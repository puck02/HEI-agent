"""
RAG Engine — retrieval with Qdrant vector store + reranking.

Supports multi-collection search across health, medication, and TCM knowledge.
Used when demo_mode=false (production).
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from qdrant_client import AsyncQdrantClient, models

from app.config import get_settings
from app.llm.router import get_llm_router

log = structlog.get_logger(__name__)

# Collection names
COLLECTIONS = {
    "health": "health_knowledge",
    "medication": "medication_info",
    "tcm": "tcm_wellness",
}


class RAGEngine:
    def __init__(self) -> None:
        settings = get_settings()
        self.client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )
        self.top_k = settings.rag_top_k
        self.rerank_top_k = settings.rag_rerank_top_k
        self.dashscope_api_key = settings.dashscope_api_key
        self._httpx: httpx.AsyncClient | None = None

    async def ensure_collections(self) -> None:
        """Create collections if they don't exist."""
        existing = await self.client.get_collections()
        existing_names = {c.name for c in existing.collections}

        for key, name in COLLECTIONS.items():
            if name not in existing_names:
                await self.client.create_collection(
                    collection_name=name,
                    vectors_config=models.VectorParams(
                        size=1024,  # text-embedding-v4 dimension
                        distance=models.Distance.COSINE,
                    ),
                )
                log.info("qdrant_collection_created", name=name)

    async def retrieve(
        self,
        query: str,
        collections: list[str] | None = None,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[dict]:
        """
        Retrieve relevant chunks from one or more collections.

        Args:
            query: Search query text
            collections: List of collection keys (health/medication/tcm). Default: all.
            top_k: Number of results to return (after reranking)
            filters: Optional Qdrant payload filters

        Returns:
            List of {content, source, score, collection} dicts
        """
        top_k = top_k or self.top_k
        target_collections = [
            COLLECTIONS[c] for c in (collections or COLLECTIONS.keys())
            if c in COLLECTIONS
        ]

        if not target_collections:
            return []

        # Generate query embedding
        router = get_llm_router()
        try:
            q_embedding = (await router.embed([query]))[0]
        except Exception as e:
            log.error("embedding_failed", error=str(e))
            return []

        # Search across collections
        all_results: list[dict] = []
        for coll_name in target_collections:
            try:
                query_params: dict[str, Any] = {
                    "collection_name": coll_name,
                    "query": q_embedding,
                    "limit": self.rerank_top_k,
                    "with_payload": True,
                }

                if filters:
                    query_params["query_filter"] = models.Filter(
                        must=[
                            models.FieldCondition(
                                key=k,
                                match=models.MatchValue(value=v),
                            )
                            for k, v in filters.items()
                        ]
                    )

                response = await self.client.query_points(**query_params)

                for hit in response.points:
                    payload = hit.payload or {}
                    all_results.append({
                        "content": payload.get("content", ""),
                        "source": payload.get("source", "unknown"),
                        "category": payload.get("category", ""),
                        "score": hit.score,
                        "collection": coll_name,
                    })

            except Exception as e:
                log.warning("qdrant_search_failed", collection=coll_name, error=str(e))

        # Sort by score, then rerank with DashScope
        all_results.sort(key=lambda x: x["score"], reverse=True)
        candidates = all_results[:self.rerank_top_k]
        
        if self.dashscope_api_key and len(candidates) > top_k:
            try:
                candidates = await self._rerank(query, candidates, top_k)
            except Exception:
                log.exception("rerank_failed")
        
        return candidates[:top_k]
    
    async def _get_httpx(self) -> httpx.AsyncClient:
        if self._httpx is None:
            self._httpx = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        return self._httpx
    
    async def _rerank(
        self,
        query: str,
        docs: list[dict],
        top_n: int,
    ) -> list[dict]:
        """Call DashScope Rerank API with qwen3-vl-rerank model."""
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
                "top_n": min(top_n, len(documents)),
                "return_documents": True,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        
        results: list[dict] = []
        for item in data.get("output", {}).get("results", []):
            idx = item.get("index", 0)
            if idx < len(docs):
                results.append({
                    **docs[idx],
                    "score": item.get("relevance_score", 0.0),
                })
        return results

    async def retrieve_with_refs(
        self,
        query: str,
        collections: list[str] | None = None,
        top_k: int | None = None,
    ) -> tuple[str, list[dict]]:
        """Retrieve and return both context string AND document references."""
        results = await self.retrieve(query, collections, top_k)
        if not results:
            return "", []
        
        context_parts = []
        refs: list[dict] = []
        seen_sources: set[str] = set()
        for i, r in enumerate(results, 1):
            source = r.get("source", "unknown")
            ctx_src = f"[{r['collection']}:{source}]" if source else f"[{r['collection']}]"
            context_parts.append(f"{i}. {ctx_src}\n{r['content']}")
            if source and source not in seen_sources:
                seen_sources.add(source)
                refs.append({
                    "index": i,
                    "source": source,
                    "collection": r["collection"],
                    "score": round(r["score"], 3),
                })
        
        return "\n\n".join(context_parts), refs

    async def retrieve_as_context(
        self,
        query: str,
        collections: list[str] | None = None,
        top_k: int | None = None,
    ) -> str:
        """Retrieve and format as a context string for LLM prompts."""
        results = await self.retrieve(query, collections, top_k)
        if not results:
            return ""
        chunks = []
        for i, r in enumerate(results, 1):
            source_info = f"[来源: {r['source']}]" if r.get("source") != "unknown" else ""
            chunks.append(f"【参考{i}】{source_info}\n{r['content']}")
        return "\n\n".join(chunks)

    async def ingest_file(
        self,
        file_path,
        collection_key: str,
        **kwargs,
    ) -> int:
        """Ingest a single document into Qdrant. Delegates to ingest module."""
        from pathlib import Path as _Path
        from app.rag.ingest import ingest_file as _ingest_file
        return await _ingest_file(
            _Path(file_path),
            collection_key,
            **kwargs,
        )

    async def close(self) -> None:
        await self.client.close()


# Singleton
_instance: RAGEngine | None = None


def get_rag_engine() -> RAGEngine:
    global _instance
    if _instance is None:
        _instance = RAGEngine()
    return _instance
