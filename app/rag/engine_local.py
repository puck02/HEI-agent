"""
RAG Engine — Qdrant local storage mode.

Uses Qdrant's built-in local storage (no Docker/service needed).
Falls back to this when demo_mode=true but qdrant-client is installed.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import structlog
from qdrant_client import QdrantClient, models

from app.config import get_settings

log = structlog.get_logger(__name__)

# Collection names
COLLECTIONS = {
    "health": "health_knowledge",
    "medication": "medication_info",
    "tcm": "tcm_wellness",
}

# Local storage path
LOCAL_STORAGE_PATH = Path.home() / ".hei-agent" / "qdrant_storage"


class RAGEngineLocal:
    """Qdrant local storage engine — no external service needed."""
    
    def __init__(self) -> None:
        settings = get_settings()
        
        # Ensure storage directory exists
        LOCAL_STORAGE_PATH.mkdir(parents=True, exist_ok=True)
        
        # Use local storage mode
        self.client = QdrantClient(path=str(LOCAL_STORAGE_PATH))
        self.top_k = settings.rag_top_k
        self.rerank_top_k = settings.rag_rerank_top_k
        self.dashscope_api_key = settings.dashscope_api_key
        self._httpx: httpx.AsyncClient | None = None
        
        log.info(
            "rag_engine_local_init",
            storage_path=str(LOCAL_STORAGE_PATH),
            top_k=self.top_k,
            rerank_top_k=self.rerank_top_k,
            rerank_enabled=bool(self.dashscope_api_key),
        )
    
    async def ensure_collections(self) -> None:
        """Create collections if they don't exist."""
        existing = self.client.get_collections()
        existing_names = {c.name for c in existing.collections}
        
        for key, name in COLLECTIONS.items():
            if name not in existing_names:
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=models.VectorParams(
                        size=1536,  # Default embedding dimension
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
        """Retrieve relevant chunks from one or more collections."""
        top_k = top_k or self.top_k
        target_collections = [
            COLLECTIONS[c] for c in (collections or COLLECTIONS.keys())
            if c in COLLECTIONS
        ]
        
        if not target_collections:
            return []
        
        # Generate query embedding
        from app.llm.router import get_llm_router
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
                results = self.client.search(
                    collection_name=coll_name,
                    query_vector=q_embedding,
                    limit=self.rerank_top_k,
                    with_payload=True,
                )
                
                for hit in results:
                    all_results.append({
                        "content": hit.payload.get("content", ""),
                        "source": hit.payload.get("source", ""),
                        "collection": coll_name,
                        "score": hit.score,
                    })
            except Exception as e:
                log.warning("collection_search_failed", collection=coll_name, error=str(e))
        
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
        """Retrieve and format as context string for LLM."""
        results = await self.retrieve(query, collections, top_k)
        
        if not results:
            return ""
        
        context_parts = []
        for i, r in enumerate(results, 1):
            source = f"[{r['collection']}:{r['source']}]" if r['source'] else f"[{r['collection']}]"
            context_parts.append(f"{i}. {source}\n{r['content']}")
        
        return "\n\n".join(context_parts)
    
    async def ingest_file(
        self,
        file_path: Path,
        collection_key: str,
        category: str = "",
        subcategory: str = "",
    ) -> int:
        """Ingest a single file into a collection."""
        from app.rag.ingest import LOADERS, _load_text, _load_pdf
        
        suffix = file_path.suffix.lower()
        if suffix not in LOADERS:
            raise ValueError(f"Unsupported file type: {suffix}")
        
        if collection_key not in COLLECTIONS:
            raise ValueError(f"Unknown collection: {collection_key}")
        
        # Load document
        text = LOADERS[suffix](file_path)
        if not text.strip():
            log.warning("empty_document", path=str(file_path))
            return 0
        
        # Split into chunks
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        settings = get_settings()
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
            separators=["\n\n", "\n", "。", "；", "，", " ", ""],
        )
        chunks = splitter.split_text(text)
        
        if not chunks:
            return 0
        
        # Generate embeddings
        from app.llm.router import get_llm_router
        router = get_llm_router()
        try:
            embeddings = await router.embed(chunks)
        except Exception as e:
            log.error("embedding_failed", error=str(e))
            # Fallback: use random embeddings for demo
            import numpy as np
            embeddings = [np.random.randn(1536).tolist() for _ in chunks]
        
        # Prepare points
        import uuid
        import hashlib
        collection_name = COLLECTIONS[collection_key]
        
        points = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{file_path}:{i}"))
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "content": chunk,
                        "source": file_path.name,
                        "category": category,
                        "subcategory": subcategory,
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                        "content_hash": hashlib.md5(chunk.encode()).hexdigest(),
                    },
                )
            )
        
        # Upsert to Qdrant
        self.client.upsert(
            collection_name=collection_name,
            points=points,
        )
        
        log.info(
            "document_ingested",
            file=file_path.name,
            collection=collection_name,
            chunks=len(chunks),
        )
        return len(chunks)
    
    async def close(self) -> None:
        """Close the client (no-op for local mode)."""
        pass


# Singleton
_instance: RAGEngineLocal | None = None


def get_rag_engine_local() -> RAGEngineLocal:
    """Get or create the local RAG engine singleton."""
    global _instance
    if _instance is None:
        _instance = RAGEngineLocal()
    return _instance
