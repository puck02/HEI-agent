"""ContextAssembler — centralised context loading for pipelines."""

from __future__ import annotations

import asyncio
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.providers.health_data import fetch_health_context
from app.context.providers.medication_data import fetch_medication_context
from app.context.providers.memory_provider import fetch_long_term_memories
from app.context.providers.rag_provider import fetch_rag_context, fetch_rag_with_refs, should_use_rag
from app.config import get_settings
from app.memory.manager import get_memory_manager

log = structlog.get_logger(__name__)


class ContextAssembler:
    """Loads and assembles all context sources in parallel.

    Replaces the scattered loading logic previously in chat.py and orchestrator.py.
    """

    def __init__(self, db: AsyncSession | None = None) -> None:
        self._db = db

    async def load_all(
        self,
        user_id: uuid.UUID,
        session_id: str,
        message: str,
        intent: str = "",
    ) -> dict:
        """Load health, medication, long-term memory, RAG, and conversation history in parallel.

        Args:
            user_id: The user's UUID.
            session_id: Conversation session ID.
            message: The user's message text.
            intent: Classified intent (health/medication/insight/general).
                    Used by RAGDecider to improve retrieval decisions.

        Returns a dict with keys:
            health_context, medication_context, long_term_memories,
            knowledge_context, conversation_history
        """
        settings = get_settings()
        memory_mgr = get_memory_manager()
        need_rag = should_use_rag(message, intent=intent)
        need_heavy_context = need_rag or len(message.strip()) > 6

        async def _health() -> str:
            if not self._db or not need_heavy_context:
                return ""
            return await fetch_health_context(self._db, user_id)

        async def _medication() -> str:
            if not self._db or not need_heavy_context:
                return ""
            return await fetch_medication_context(self._db, user_id)

        async def _memories() -> list[str]:
            if not self._db:
                return []
            return await fetch_long_term_memories(
                self._db, user_id, session_id, message
            )

        async def _rag() -> tuple[str, list[dict]]:
            if not need_rag:
                return "", []
            return await fetch_rag_with_refs(message)

        async def _history() -> str:
            try:
                return await memory_mgr.short_term.get_formatted_history(
                    session_id,
                    max_messages=settings.chat_history_max_messages,
                    max_chars=settings.chat_history_max_chars,
                )
            except Exception:
                return ""

        health_ctx, med_ctx, memories, (knowledge_ctx, knowledge_refs), history = await asyncio.gather(
            _health(), _medication(), _memories(), _rag(), _history()
        )

        return {
            "health_context": health_ctx,
            "medication_context": med_ctx,
            "long_term_memories": memories,
            "knowledge_context": knowledge_ctx,
            "knowledge_refs": knowledge_refs,
            "conversation_history": history,
        }
