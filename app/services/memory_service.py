"""
Lightweight memory service using SQLite keyword search only.

Design (inspired by Hermes Agent):
- MEMORY.md  → agent notes, injected into system prompt every turn
- USER.md    → static user profile, injected into system prompt
- memories   → SQLite table for long-term facts, searched via keywords
- sessions   → SQLite table for session summaries (for cross-session recall)

The LLM decides when to search and what keywords to use.
No embedding, no BM25, no Rerank — pure keyword matching.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory

log = logging.getLogger(__name__)

# ── SQL table init ──────────────────────────────────────────────

async def _ensure_tables() -> None:
    """Create memory tables if they don't exist."""
    async with async_session_factory() as session:
        await session.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_memories (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                memory_type TEXT DEFAULT 'general',
                importance REAL DEFAULT 0.5,
                created_at TEXT NOT NULL
            )
        """))
        await session.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_session_summaries (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """))
        await session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_memories_user
            ON agent_memories(user_id)
        """))
        await session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_memories_user_type
            ON agent_memories(user_id, memory_type)
        """))
        await session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_session_summaries_user
            ON agent_session_summaries(user_id)
        """))
        await session.commit()


class MemoryService:
    """SQLite-based memory: keyword search only, no vectors."""

    def __init__(self) -> None:
        self._tables_ensured = False

    async def _init(self) -> None:
        if not self._tables_ensured:
            await _ensure_tables()
            self._tables_ensured = True

    # ── Search ───────────────────────────────────────────

    async def search_memory(
        self,
        user_id: str,
        keywords: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Keyword search across memories.

        LLM provides keywords like "青霉素 过敏" and we do LIKE matching.
        Also searches session summaries for cross-session context.
        """
        await self._init()
        terms = [t.strip() for t in keywords.split() if t.strip()]

        async with async_session_factory() as session:
            rows = await self._search_terms(session, user_id, terms, top_k)
            return rows

    async def _search_terms(
        self,
        session: AsyncSession,
        user_id: str,
        terms: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Build LIKE clauses from keywords and execute."""
        if not terms:
            # No keywords — return recent memories
            result = await session.execute(
                text("""
                    SELECT id, content, memory_type, importance, created_at
                    FROM agent_memories
                    WHERE user_id = :uid
                    ORDER BY created_at DESC
                    LIMIT :lim
                """),
                {"uid": user_id, "lim": top_k},
            )
            return [dict(r._mapping) for r in result]

        # Build OR LIKE clauses
        conditions = " OR ".join(f"content LIKE :t{i}" for i in range(len(terms)))
        params = {"uid": user_id, "lim": top_k}
        for i, t in enumerate(terms):
            params[f"t{i}"] = f"%{t}%"

        query = text(f"""
            SELECT id, content, memory_type, importance, created_at
            FROM agent_memories
            WHERE user_id = :uid AND ({conditions})
            ORDER BY created_at DESC
            LIMIT :lim
        """)

        result = await session.execute(query, params)
        return [dict(r._mapping) for r in result]

    # ── Remember ─────────────────────────────────────────

    async def remember(
        self,
        user_id: str,
        content: str,
        memory_type: str = "general",
        importance: float = 0.7,
    ) -> str:
        """Store a fact into SQLite memory."""
        await self._init()
        memory_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        async with async_session_factory() as session:
            await session.execute(
                text("""
                    INSERT INTO agent_memories (id, user_id, content, memory_type, importance, created_at)
                    VALUES (:id, :uid, :content, :type, :imp, :created)
                """),
                {
                    "id": memory_id,
                    "uid": user_id,
                    "content": content,
                    "type": memory_type,
                    "imp": importance,
                    "created": now,
                },
            )
            await session.commit()

        log.info("memory_stored", id=memory_id, type=memory_type)
        return memory_id

    # ── Session Summaries ────────────────────────────────

    async def save_session_summary(
        self,
        user_id: str,
        session_id: str,
        summary: str,
    ) -> str:
        """Store a session summary for future cross-session recall."""
        await self._init()
        sid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        async with async_session_factory() as session:
            await session.execute(
                text("""
                    INSERT INTO agent_session_summaries (id, user_id, session_id, summary, created_at)
                    VALUES (:id, :uid, :sid, :summary, :created)
                """),
                {
                    "id": sid,
                    "uid": user_id,
                    "sid": session_id,
                    "summary": summary,
                    "created": now,
                },
            )
            await session.commit()
        return sid

    async def search_sessions(
        self,
        user_id: str,
        keywords: str,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """Keyword search across session summaries."""
        await self._init()
        terms = [t.strip() for t in keywords.split() if t.strip()]

        async with async_session_factory() as session:
            if not terms:
                result = await session.execute(
                    text("""
                        SELECT id, session_id, summary, created_at
                        FROM agent_session_summaries
                        WHERE user_id = :uid
                        ORDER BY created_at DESC
                        LIMIT :lim
                    """),
                    {"uid": user_id, "lim": top_k},
                )
                return [dict(r._mapping) for r in result]

            conditions = " OR ".join(f"summary LIKE :t{i}" for i in range(len(terms)))
            params = {"uid": user_id, "lim": top_k}
            for i, t in enumerate(terms):
                params[f"t{i}"] = f"%{t}%"

            result = await session.execute(
                text(f"""
                    SELECT id, session_id, summary, created_at
                    FROM agent_session_summaries
                    WHERE user_id = :uid AND ({conditions})
                    ORDER BY created_at DESC
                    LIMIT :lim
                """),
                params,
            )
            return [dict(r._mapping) for r in result]
