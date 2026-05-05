from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

try:
    from app.rag.engine import get_rag_engine
    _RAG_AVAILABLE = True
except ImportError:
    _RAG_AVAILABLE = False
    log.warning("rag_unavailable", detail="RAG engine not available; all searches will return empty lists")


class KnowledgeService:
    """Async wrapper around the RAG engine for domain-specific knowledge searches."""

    @staticmethod
    async def search_health(query: str) -> list[dict[str, Any]]:
        return await KnowledgeService._search(query, collections=["health"], top_k=5)

    @staticmethod
    async def search_medication(query: str) -> list[dict[str, Any]]:
        return await KnowledgeService._search(query, collections=["medication"], top_k=5)

    @staticmethod
    async def search_tcm(query: str) -> list[dict[str, Any]]:
        return await KnowledgeService._search(query, collections=["tcm"], top_k=5)

    @staticmethod
    async def search_all(query: str) -> list[dict[str, Any]]:
        return await KnowledgeService._search(query, collections=None, top_k=5)

    @staticmethod
    async def _search(
        query: str,
        collections: list[str] | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        if not _RAG_AVAILABLE:
            return []
        try:
            engine = get_rag_engine()
            return await engine.retrieve(query=query, collections=collections, top_k=top_k)
        except Exception:
            log.exception("knowledge_search_failed query=%s", query[:100])
            return []
