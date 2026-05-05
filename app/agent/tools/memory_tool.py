"""Async tool wrappers for the lightweight SQLite memory system."""

from __future__ import annotations

import logging

from app.services.memory_service import MemoryService
from app.services.profile_service import ProfileService

log = logging.getLogger(__name__)


async def search_memory(user_id: str, keywords: str) -> str:
    """
    Search user's long-term memories by keywords.

    The LLM decides what keywords to search for — e.g., "青霉素 过敏"
    or "咖啡 偏好". Returns matching memories sorted by recency.
    """
    try:
        service = MemoryService()
        results = await service.search_memory(user_id=user_id, keywords=keywords, top_k=5)
    except Exception:
        log.exception("search_memory_failed")
        return "Memory search failed."

    if not results:
        return f"No memories found for keywords: {keywords}"

    lines: list[str] = [f"Found {len(results)} memories:"]
    for i, mem in enumerate(results, start=1):
        content = mem.get("content", "")
        mtype = mem.get("memory_type", "general")
        created = mem.get("created_at", "")[:10]
        lines.append(f"  #{i} [{mtype}] ({created}) {content}")

    return "\n".join(lines)


async def remember(user_id: str, fact: str) -> str:
    """
    Store an important fact into long-term memory (SQLite).

    Also appends the fact to MEMORY.md for system prompt injection.
    Requires user confirmation before execution.
    """
    try:
        # Store in SQLite
        service = MemoryService()
        memory_id = await service.remember(
            user_id=user_id,
            content=fact,
            memory_type="user_fact",
            importance=0.7,
        )

        # Also append to MEMORY.md
        profile = ProfileService()
        profile.add_memory_fact(user_id, fact)
    except Exception:
        log.exception("remember_failed")
        return "Failed to store memory."

    return f"✅ Remembered: {fact} (id: {memory_id[:8]}...)"


async def search_sessions(user_id: str, keywords: str) -> str:
    """
    Search past conversation session summaries by keywords.

    Useful when the user references "last time we talked about X".
    """
    try:
        service = MemoryService()
        results = await service.search_sessions(user_id=user_id, keywords=keywords, top_k=3)
    except Exception:
        log.exception("search_sessions_failed")
        return "Session search failed."

    if not results:
        return f"No past sessions found for keywords: {keywords}"

    lines: list[str] = [f"Found {len(results)} past sessions:"]
    for i, s in enumerate(results, start=1):
        summary = s.get("summary", "")[:150]
        created = s.get("created_at", "")[:10]
        lines.append(f"  #{i} ({created}) {summary}")

    return "\n".join(lines)
