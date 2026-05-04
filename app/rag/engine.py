"""
RAG Engine — config-driven router.

Routes to the appropriate implementation based on settings and available dependencies:
  - demo_mode=true  → local Qdrant engine (no external service needed)
  - demo_mode=false → Qdrant-based engine (engine_qdrant.py, requires Qdrant service)

Public interface: RAGEngine class, get_rag_engine() function.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.config import get_settings

log = structlog.get_logger(__name__)

# Collection names (shared by all implementations)
COLLECTIONS = {
    "health": "health_knowledge",
    "medication": "medication_info",
    "tcm": "tcm_wellness",
}

settings = get_settings()

# Try to import local engine first (preferred for demo mode)
_local_available = False
try:
    from app.rag.engine_local import RAGEngineLocal, get_rag_engine_local
    _local_available = True
except ImportError as exc:
    log.debug("local_engine_import_failed", error=str(exc))

# Try to import Qdrant engine (for production mode)
_qdrant_available = False
try:
    from app.rag.engine_qdrant import RAGEngine as QdrantRAGEngine
    _qdrant_available = True
except ImportError as exc:
    log.debug("qdrant_engine_import_failed", error=str(exc))


if settings.demo_mode and not settings.qdrant_url:
    # QDRANT_URL not set → use local engine or stub
    if _local_available:
        # ── Local Qdrant engine (demo mode with local storage) ──────────────
        log.info("rag_engine_selected", engine="local", reason="demo_mode with local Qdrant")
        
        class RAGEngine:
            """Demo RAGEngine with local Qdrant storage."""
            
            def __init__(self) -> None:
                self._local = RAGEngineLocal()
                self.top_k = settings.rag_top_k
                self.rerank_top_k = settings.rag_rerank_top_k
                log.info("rag_engine_init", mode="local_demo")
            
            async def ensure_collections(self) -> None:
                await self._local.ensure_collections()
            
            async def retrieve(
                self,
                query: str,
                collections: list[str] | None = None,
                top_k: int | None = None,
                filters: dict[str, Any] | None = None,
            ) -> list[dict]:
                return await self._local.retrieve(query, collections, top_k, filters)
            
            async def retrieve_as_context(
                self,
                query: str,
                collections: list[str] | None = None,
                top_k: int | None = None,
            ) -> str:
                return await self._local.retrieve_as_context(query, collections, top_k)
            
            async def retrieve_with_refs(
                self,
                query: str,
                collections: list[str] | None = None,
                top_k: int | None = None,
            ) -> tuple:
                return await self._local.retrieve_with_refs(query, collections, top_k)
            
            async def ingest_file(self, file_path, collection_key, **kwargs) -> int:
                return await self._local.ingest_file(file_path, collection_key, **kwargs)
            
            async def close(self) -> None:
                await self._local.close()
    
    else:
        # ── Stub implementation (no vector store at all) ────────────────────
        log.info("rag_engine_selected", engine="stub", reason="demo_mode, no local Qdrant available")
        
        class RAGEngine:
            """Demo RAGEngine — returns empty results (no vector store)."""
            
            def __init__(self) -> None:
                self.top_k = settings.rag_top_k
                self.rerank_top_k = settings.rag_rerank_top_k
                log.info("rag_engine_init", mode="demo_stub", note="No vector store configured")
            
            async def ensure_collections(self) -> None:
                log.info("rag_collections_skipped", reason="demo_mode")
            
            async def retrieve(self, query: str, **kwargs: Any) -> list[dict]:
                log.debug("rag_retrieve_skipped", query=query[:50], reason="demo_mode")
                return []
            
            async def retrieve_as_context(self, query: str, **kwargs: Any) -> str:
                log.debug("rag_context_skipped", query=query[:50], reason="demo_mode")
                return ""
            
            async def retrieve_with_refs(self, query: str, **kwargs: Any) -> tuple:
                log.debug("rag_context_skipped", query=query[:50], reason="demo_mode")
                return "", []
            
            async def ingest_file(self, *args, **kwargs) -> int:
                log.warning("rag_ingest_skipped", reason="demo_mode_stub")
                return 0
            
            async def close(self) -> None:
                pass

else:
    if _qdrant_available:
        # ── Production Qdrant engine ────────────────────────────────────────
        log.info("rag_engine_selected", engine="qdrant", reason="production mode")
        RAGEngine = QdrantRAGEngine
    
    elif _local_available:
        # ── Fallback to local engine even in "production" ───────────────────
        log.warning("rag_engine_fallback", engine="local", reason="qdrant engine not available")
        
        class RAGEngine:
            """Fallback: local Qdrant even in production mode."""
            
            def __init__(self) -> None:
                self._local = RAGEngineLocal()
                self.top_k = settings.rag_top_k
                self.rerank_top_k = settings.rag_rerank_top_k
            
            async def ensure_collections(self) -> None:
                await self._local.ensure_collections()
            
            async def retrieve(self, query: str, **kwargs: Any) -> list[dict]:
                return await self._local.retrieve(query, **kwargs)
            
            async def retrieve_as_context(self, query: str, **kwargs: Any) -> str:
                return await self._local.retrieve_as_context(query, **kwargs)
            
            async def ingest_file(self, *args, **kwargs) -> int:
                return await self._local.ingest_file(*args, **kwargs)
            
            async def close(self) -> None:
                await self._local.close()
    
    else:
        # ── No engine available ─────────────────────────────────────────────
        log.error("rag_engine_unavailable", reason="no RAG engine implementation found")
        
        class RAGEngine:
            """Stub — no RAG engine available."""
            
            def __init__(self) -> None:
                self.top_k = settings.rag_top_k
                self.rerank_top_k = settings.rag_rerank_top_k
            
            async def ensure_collections(self) -> None:
                pass
            
            async def retrieve(self, query: str, **kwargs: Any) -> list[dict]:
                return []
            
            async def retrieve_as_context(self, query: str, **kwargs: Any) -> str:
                return ""
            
            async def ingest_file(self, *args, **kwargs) -> int:
                return 0
            
            async def close(self) -> None:
                pass


# Singleton
_instance: RAGEngine | None = None


def get_rag_engine() -> RAGEngine:
    global _instance
    if _instance is None:
        _instance = RAGEngine()
    return _instance
