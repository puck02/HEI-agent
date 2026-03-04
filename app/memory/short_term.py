"""
Short-term memory — Redis-backed conversational context.

Stores per-session message history with TTL expiry and sliding window.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import redis.asyncio as redis
import structlog

from app.config import get_settings

log = structlog.get_logger(__name__)


class ShortTermMemory:
    def __init__(self) -> None:
        settings = get_settings()
        self.redis = redis.from_url(settings.redis_url, decode_responses=True)
        self.ttl = settings.short_term_memory_ttl
        self.max_turns = settings.short_term_memory_max_turns

    def _key(self, session_id: str) -> str:
        return f"stm:{session_id}"

    async def get_history(self, session_id: str) -> list[dict]:
        """Retrieve conversation history for a session."""
        raw = await self.redis.get(self._key(session_id))
        if not raw:
            return []
        try:
            messages = json.loads(raw)
            return messages[-self.max_turns * 2:]  # keep last N turns (user+assistant pairs)
        except (json.JSONDecodeError, TypeError):
            return []

    async def add_message(self, session_id: str, role: str, content: str) -> None:
        """Append a message to session history."""
        history = await self.get_history(session_id)
        history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Trim to max window
        if len(history) > self.max_turns * 2:
            history = history[-self.max_turns * 2:]
        await self.redis.set(
            self._key(session_id),
            json.dumps(history, ensure_ascii=False),
            ex=self.ttl,
        )

    async def clear(self, session_id: str) -> None:
        """Clear a session's history."""
        await self.redis.delete(self._key(session_id))

    async def get_formatted_history(self, session_id: str) -> str:
        """Return history as a formatted text block for LLM context."""
        history = await self.get_history(session_id)
        if not history:
            return ""
        lines = []
        for msg in history:
            role_label = "用户" if msg["role"] == "user" else "助手"
            lines.append(f"{role_label}: {msg['content']}")
        return "\n".join(lines)

    async def close(self) -> None:
        await self.redis.close()


# Singleton
_instance: ShortTermMemory | None = None


def get_short_term_memory() -> ShortTermMemory:
    global _instance
    if _instance is None:
        _instance = ShortTermMemory()
    return _instance
