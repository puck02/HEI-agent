"""
Hybrid memory service combining Qdrant vector search, BM25 keyword search,
and DashScope reranking for long-term user memory retrieval.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

try:
    from qdrant_client import AsyncQdrantClient, models
    _QDRANT_AVAILABLE = True
except ImportError:
    _QDRANT_AVAILABLE = False

try:
    from rank_bm25 import BM25Okapi
    _BM25_AVAILABLE = True
except ImportError:
    _BM25_AVAILABLE = False

from app.config import get_settings

log = logging.getLogger(__name__)

COLLECTION_NAME = "user_memories"
VECTOR_SIZE = 1024
RRF_K = 60


def _tokenize(text: str) -> list[str]:
    """Chinese char bigram tokenizer: sliding 2-char windows + single chars."""
    tokens: list[str] = []
    if not text:
        return tokens
    for i in range(len(text) - 1):
        tokens.append(text[i:i + 2])
    tokens.extend(list(text))
    return tokens


class MemoryService:
    """Hybrid long-term memory with vector + keyword + rerank search."""

    def __init__(self) -> None:
        settings = get_settings()

        if not _QDRANT_AVAILABLE:
            raise ImportError("qdrant-client is required for MemoryService")
        if not _BM25_AVAILABLE:
            raise ImportError("rank-bm25 is required for MemoryService")

        self.qdrant_url = settings.qdrant_url or "http://localhost:6333"
        self.qdrant_api_key = settings.qdrant_api_key
        self.dashscope_api_key = settings.dashscope_api_key

        self.client = AsyncQdrantClient(url=self.qdrant_url, api_key=self.qdrant_api_key)
        self.bm25: BM25Okapi | None = None
        self._docs: list[dict[str, Any]] = []
        self._initialized = False
        self._httpx: httpx.AsyncClient | None = None

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        if not await self.client.collection_exists(COLLECTION_NAME):
            await self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=VECTOR_SIZE,
                    distance=models.Distance.COSINE,
                ),
            )
            log.info("memory_collection_created", collection=COLLECTION_NAME)

        await self._load_bm25()
        self._initialized = True

    async def _load_bm25(self) -> None:
        """Scroll all points from Qdrant and build BM25 index from their content."""
        self._docs = []
        offset = None
        while True:
            points, next_offset = await self.client.scroll(
                collection_name=COLLECTION_NAME,
                limit=100,
                offset=offset,
                with_payload=True,
            )
            for point in points:
                if point.payload:
                    self._docs.append({
                        "id": point.id,
                        "content": point.payload.get("content", ""),
                        "type": point.payload.get("type", "general"),
                        "importance": point.payload.get("importance", 0.5),
                        "entity_tags": point.payload.get("entity_tags", []),
                    })

            if next_offset is None:
                break
            offset = next_offset

        if self._docs:
            tokenized = [_tokenize(d["content"]) for d in self._docs]
            self.bm25 = BM25Okapi(tokenized)
        else:
            self.bm25 = None
        log.info("bm25_loaded", doc_count=len(self._docs))

    async def _get_httpx(self) -> httpx.AsyncClient:
        if self._httpx is None:
            self._httpx = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        return self._httpx

    async def _get_embedding(self, text: str) -> list[float]:
        from app.llm.router import get_llm_router
        router = get_llm_router()
        embeddings = await router.embed([text])
        return embeddings[0]

    async def search_memory(
        self,
        query: str,
        user_id: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Hybrid search: vector + BM25 → RRF merge → DashScope rerank."""
        await self._ensure_initialized()

        embedding = await self._get_embedding(query)

        # Qdrant vector search
        qdrant_results = await self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=embedding,
            limit=20,
            query_filter=models.Filter(
                must=[models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id))]
            ),
            with_payload=True,
        )

        # BM25 keyword search
        bm25_results: list[tuple[int, float]] = []
        if self.bm25 is not None and self._docs:
            query_tokens = _tokenize(query)
            if query_tokens:
                scores = self.bm25.get_scores(query_tokens)
                indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
                bm25_results = indexed[:20]

        # RRF merge
        rrf_scores: dict[str, float] = {}
        rrf_docs: dict[str, dict[str, Any]] = {}

        for rank, point in enumerate(qdrant_results.points):
            doc_id = str(point.id)
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1.0 / (RRF_K + rank + 1)
            if point.payload:
                rrf_docs[doc_id] = dict(point.payload)

        for rank, (doc_idx, score) in enumerate(bm25_results):
            doc = self._docs[doc_idx]
            doc_id = str(doc["id"])
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1.0 / (RRF_K + rank + 1)
            if doc_id not in rrf_docs:
                rrf_docs[doc_id] = {
                    "content": doc["content"],
                    "type": doc["type"],
                    "importance": doc["importance"],
                    "entity_tags": doc["entity_tags"],
                }

        merged = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        deduped: list[dict[str, Any]] = []
        seen_contents: set[str] = set()
        for doc_id, rrf_score in merged:
            doc = rrf_docs.get(doc_id)
            if doc is None:
                continue
            content = doc.get("content", "")
            if content in seen_contents:
                continue
            seen_contents.add(content)
            deduped.append({**doc, "id": doc_id, "rrf_score": rrf_score})

        if not deduped:
            return []

        # DashScope Rerank
        if self.dashscope_api_key:
            try:
                reranked = await self._rerank(query, deduped, min(top_k, len(deduped)))
                return reranked[:top_k]
            except Exception:
                log.exception("rerank_failed")

        # Fallback: return RRF results directly
        results: list[dict[str, Any]] = []
        for doc in deduped[:top_k]:
            results.append({
                "content": doc.get("content", ""),
                "type": doc.get("type", "general"),
                "importance": doc.get("importance", 0.5),
                "entity_tags": doc.get("entity_tags", []),
                "score": doc.get("rrf_score", 0.0),
            })
        return results

    async def _rerank(
        self,
        query: str,
        docs: list[dict[str, Any]],
        top_n: int,
    ) -> list[dict[str, Any]]:
        """Call DashScope Rerank API and return re-ranked results."""
        http = await self._get_httpx()
        documents = [d.get("content", "") for d in docs]
        resp = await http.post(
            "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank",
            headers={
                "Authorization": f"Bearer {self.dashscope_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gte-rerank",
                "query": query,
                "documents": documents,
                "top_n": top_n,
                "return_documents": True,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        results: list[dict[str, Any]] = []
        for item in data.get("output", {}).get("results", []):
            idx = item.get("index", 0)
            results.append({
                "content": docs[idx].get("content", ""),
                "type": docs[idx].get("type", "general"),
                "importance": docs[idx].get("importance", 0.5),
                "entity_tags": docs[idx].get("entity_tags", []),
                "score": item.get("relevance_score", 0.0),
            })
        return results

    async def remember(
        self,
        user_id: str,
        content: str,
        memory_type: str = "general",
        importance: float = 0.5,
        entity_tags: list[str] | None = None,
    ) -> str:
        """Store a memory with embedding, upsert to Qdrant, and add to BM25."""
        await self._ensure_initialized()

        embedding = await self._get_embedding(content)
        memory_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        payload = {
            "content": content,
            "type": memory_type,
            "importance": importance,
            "entity_tags": entity_tags or [],
            "user_id": user_id,
            "created_at": now,
        }

        point = models.PointStruct(
            id=memory_id,
            vector=embedding,
            payload=payload,
        )
        await self.client.upsert(
            collection_name=COLLECTION_NAME,
            points=[point],
        )

        # Add to BM25 index
        self._docs.append({
            "id": memory_id,
            "content": content,
            "type": memory_type,
            "importance": importance,
            "entity_tags": entity_tags or [],
        })
        if self.bm25 is not None:
            tokenized = [_tokenize(d["content"]) for d in self._docs]
            self.bm25 = BM25Okapi(tokenized)

        log.info("memory_stored", id=memory_id, type=memory_type)
        return memory_id

    async def close(self) -> None:
        if self._httpx is not None:
            await self._httpx.aclose()
            self._httpx = None
        await self.client.close()
