"""RAG knowledge retrieval provider — uses RAGDecider for configurable retrieval decisions."""

from __future__ import annotations

import structlog

from app.rag.decider import RAGDecider
from app.rag.engine import get_rag_engine

log = structlog.get_logger(__name__)

# Module-level default decider instance
_default_decider = RAGDecider()


def should_use_rag(message: str, intent: str = "") -> bool:
    """Check whether the message should trigger RAG retrieval.

    Uses RAGDecider for semantic-based decision. The intent parameter
    allows the decider to use intent-based strategy when available.
    """
    import asyncio

    # For sync callers: run only keyword/intent checks (no LLM)
    if intent in _default_decider.always_retrieve_intents:
        return True

    # Fall back to the fast synchronous keyword check
    from app.rag.decider import _RAG_KEYWORDS

    return bool(_RAG_KEYWORDS.search(message))


async def should_use_rag_async(
    message: str,
    intent: str = "",
    *,
    enable_llm_check: bool = False,
    decider: RAGDecider | None = None,
) -> bool:
    """Async version: full RAGDecider evaluation including optional LLM check."""
    d = decider or _default_decider
    return await d.should_retrieve(message, intent, enable_llm_check=enable_llm_check)


async def fetch_rag_context(query: str, top_k: int = 3) -> str:
    """Retrieve knowledge context from RAG engine (context string only)."""
    try:
        rag = get_rag_engine()
        return await rag.retrieve_as_context(query=query, top_k=top_k)
    except Exception as e:
        log.warning("rag_retrieval_failed", error=str(e))
        return ""


async def fetch_rag_with_refs(
    query: str,
    top_k: int = 3,
    collections: list[str] | None = None,
) -> tuple[str, list[dict]]:
    """Retrieve knowledge context AND document references from RAG engine.

    Returns:
        (context_string, references_list)
        references_list is a list of dicts with {index, source, collection, score}
    """
    try:
        rag = get_rag_engine()
        return await rag.retrieve_with_refs(
            query=query, collections=collections, top_k=top_k,
        )
    except Exception as e:
        log.warning("rag_retrieval_with_refs_failed", error=str(e))
        return "", []
