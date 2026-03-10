"""
RAG Engine — retrieval with Qdrant vector store + reranking.

Supports multi-collection search across health, medication, and TCM knowledge.
"""

from __future__ import annotations

from typing import Any

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

    async def ensure_collections(self) -> None:
        """Create collections if they don't exist."""
        existing = await self.client.get_collections()
        existing_names = {c.name for c in existing.collections}

        for key, name in COLLECTIONS.items():
            if name not in existing_names:
                await self.client.create_collection(
                    collection_name=name,
                    vectors_config=models.VectorParams(
                        size=2048,  # embedding-3 dimension
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

        # Sort by score and return top-k
        all_results.sort(key=lambda x: x["score"], reverse=True)
        return all_results[:top_k]

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

    async def close(self) -> None:
        await self.client.close()


# Singleton
_instance: RAGEngine | None = None


def get_rag_engine() -> RAGEngine:
    global _instance
    if _instance is None:
        _instance = RAGEngine()
    return _instance
