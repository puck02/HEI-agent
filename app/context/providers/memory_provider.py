"""Long-term memory provider — semantic recall via pgvector."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.manager import get_memory_manager

log = structlog.get_logger(__name__)


async def fetch_long_term_memories(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: str,
    query: str,
    top_k: int = 5,
) -> list[str]:
    """Retrieve long-term memories relevant to the query."""
    try:
        memory_mgr = get_memory_manager()
        result = await memory_mgr.recall(
            db=db,
            user_id=user_id,
            session_id=session_id,
            query=query,
            top_k=top_k,
        )
        return result.get("relevant_memories", [])
    except Exception as e:
        log.warning("long_term_recall_failed", error=str(e))
        return []
