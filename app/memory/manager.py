"""
Memory Manager — orchestates short-term (Redis) + long-term (PostgreSQL) memory.

Provides a unified interface for the Agent layer to recall context
and store new memories from conversations.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.router import get_llm_router
from app.memory.long_term import get_long_term_memory
from app.memory.short_term import get_short_term_memory
from app.utils.json_parser import parse_llm_json

log = structlog.get_logger(__name__)


class MemoryManager:
    def __init__(self) -> None:
        self.short_term = get_short_term_memory()
        self.long_term = get_long_term_memory()

    async def recall(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        session_id: str,
        query: str,
        top_k: int = 5,
    ) -> dict:
        """
        Retrieve comprehensive context from both memory systems.

        Returns:
            {
                "conversation_history": str,   # recent chat context
                "relevant_memories": [str],    # long-term relevant memories
            }
        """
        # Short-term: conversation history
        history = await self.short_term.get_formatted_history(session_id)

        # Long-term: semantically relevant memories
        memories = await self.long_term.recall(
            db, user_id, query=query, top_k=top_k
        )
        memory_texts = [m.content for m in memories]

        return {
            "conversation_history": history,
            "relevant_memories": memory_texts,
        }

    async def memorize_conversation(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        session_id: str,
        user_message: str,
        assistant_response: str,
    ) -> None:
        """Store conversation turn in short-term and optionally extract long-term memory."""
        # Always store in short-term
        await self.short_term.add_message(session_id, "user", user_message)
        await self.short_term.add_message(session_id, "assistant", assistant_response)

    async def extract_and_store_insights(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        conversation_text: str,
    ) -> None:
        """
        Use LLM to extract important health insights from a conversation
        and store them as long-term memories.
        """
        router = get_llm_router()

        prompt = f"""请从以下对话中提取重要的健康相关信息，用于长期记忆。
只提取以下类型的信息（JSON 数组），每条不超过 50 字：
- health_pattern: 用户的健康模式/习惯
- preference: 用户的偏好/生活方式
- medical_history: 用药/就医相关信息

对话内容：
{conversation_text}

输出格式（JSON）：
[{{"type": "health_pattern", "content": "..."}}, ...]
如果没有值得记录的信息，输出空数组 []。"""

        try:
            result = await router.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=512,
                response_format={"type": "json_object"},
            )

            data = parse_llm_json(result.content)
            insights = data if isinstance(data, list) else data.get("insights", [])

            for item in insights:
                if isinstance(item, dict) and "type" in item and "content" in item:
                    await self.long_term.store(
                        db,
                        user_id,
                        content=item["content"],
                        memory_type=item["type"],
                        importance=0.8,
                    )

            if insights:
                log.info("memory_insights_extracted", count=len(insights))

        except Exception as e:
            log.warning("memory_extraction_failed", error=str(e))

    async def clear_session(self, session_id: str) -> None:
        """Clear short-term memory for a session."""
        await self.short_term.clear(session_id)


# Singleton
_instance: MemoryManager | None = None


def get_memory_manager() -> MemoryManager:
    global _instance
    if _instance is None:
        _instance = MemoryManager()
    return _instance
