"""Async tool wrappers around MemoryService for agent use."""

from __future__ import annotations

import logging

from app.services.memory_service import MemoryService

log = logging.getLogger(__name__)


async def search_memory(user_id: str, query: str) -> str:
    """Search long-term memory and return human-readable results."""
    try:
        service = MemoryService()
        results = await service.search_memory(query=query, user_id=user_id, top_k=5)
    except Exception:
        log.exception("search_memory_failed")
        return "Memory search failed due to an internal error."

    if not results:
        return "No memories found."

    lines: list[str] = []
    for i, mem in enumerate(results, start=1):
        content = mem.get("content", "")
        mtype = mem.get("type", "general")
        importance = mem.get("importance", 0.0)
        lines.append(f"Memory #{i}: {content} (type: {mtype}, importance: {importance})")

    return "\n".join(lines)


async def remember(user_id: str, fact: str) -> str:
    """Store a user fact into long-term memory."""
    try:
        service = MemoryService()
        memory_id = await service.remember(
            user_id=user_id,
            content=fact,
            memory_type="user_fact",
            importance=0.7,
        )
    except Exception:
        log.exception("remember_failed")
        return "Failed to store memory due to an internal error."

    return f"Memory stored: {memory_id}"
