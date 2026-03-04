"""
Long-term memory — PostgreSQL-backed persistent memory with embeddings.

Stores health patterns, user preferences, medical history summaries,
and conversation summaries. Supports semantic retrieval via pgvector.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import desc, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.llm.router import get_llm_router
from app.models.memory import MemoryEntry

log = structlog.get_logger(__name__)

MEMORY_TYPES = ("health_pattern", "preference", "medical_history", "conversation_summary")


class LongTermMemory:

    async def store(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        content: str,
        memory_type: str,
        importance: float = 1.0,
        metadata: dict | None = None,
    ) -> MemoryEntry:
        """Store a new long-term memory with auto-generated embedding."""
        if memory_type not in MEMORY_TYPES:
            raise ValueError(f"Invalid memory_type: {memory_type}. Must be one of {MEMORY_TYPES}")

        # Generate embedding
        embedding = None
        try:
            router = get_llm_router()
            embeddings = await router.embed([content])
            if embeddings:
                embedding = embeddings[0]
        except Exception as e:
            log.warning("embedding_generation_failed", error=str(e))

        entry = MemoryEntry(
            user_id=user_id,
            memory_type=memory_type,
            content=content,
            importance_score=importance,
            embedding=embedding,
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
        )
        db.add(entry)
        await db.flush()
        return entry

    async def recall(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        query: str | None = None,
        memory_type: str | None = None,
        top_k: int = 5,
    ) -> list[MemoryEntry]:
        """
        Retrieve relevant memories.
        If query is provided and embeddings are available, use cosine similarity.
        Otherwise, fall back to recency + importance ordering.
        """
        # Try semantic search if query is provided
        if query:
            try:
                router = get_llm_router()
                q_embedding = (await router.embed([query]))[0]

                # Use pgvector cosine distance if available
                # Fallback: simple ordering by importance and recency
                stmt = (
                    select(MemoryEntry)
                    .where(MemoryEntry.user_id == user_id)
                    .where(MemoryEntry.embedding.isnot(None))
                )
                if memory_type:
                    stmt = stmt.where(MemoryEntry.memory_type == memory_type)

                stmt = stmt.order_by(
                    desc(MemoryEntry.importance_score),
                    desc(MemoryEntry.last_accessed_at),
                ).limit(top_k * 2)

                result = await db.execute(stmt)
                candidates = list(result.scalars().all())

                # In-memory cosine similarity reranking
                if candidates and q_embedding:
                    scored = []
                    for mem in candidates:
                        if mem.embedding:
                            sim = self._cosine_similarity(q_embedding, mem.embedding)
                            scored.append((sim, mem))
                    scored.sort(key=lambda x: x[0], reverse=True)
                    memories = [m for _, m in scored[:top_k]]

                    # Update last_accessed_at
                    for mem in memories:
                        mem.last_accessed_at = datetime.now(timezone.utc)
                    await db.flush()
                    return memories

            except Exception as e:
                log.warning("semantic_recall_failed", error=str(e))

        # Fallback: importance + recency
        stmt = (
            select(MemoryEntry)
            .where(MemoryEntry.user_id == user_id)
        )
        if memory_type:
            stmt = stmt.where(MemoryEntry.memory_type == memory_type)
        stmt = stmt.order_by(
            desc(MemoryEntry.importance_score),
            desc(MemoryEntry.last_accessed_at),
        ).limit(top_k)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def decay_memories(self, db: AsyncSession, user_id: uuid.UUID) -> int:
        """Apply time-based decay to importance scores."""
        settings = get_settings()
        rate = settings.long_term_memory_decay_rate
        stmt = (
            update(MemoryEntry)
            .where(MemoryEntry.user_id == user_id)
            .where(MemoryEntry.importance_score > 0.1)
            .values(importance_score=MemoryEntry.importance_score * rate)
        )
        result = await db.execute(stmt)
        await db.flush()
        return result.rowcount

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


# Singleton
_instance: LongTermMemory | None = None


def get_long_term_memory() -> LongTermMemory:
    global _instance
    if _instance is None:
        _instance = LongTermMemory()
    return _instance
