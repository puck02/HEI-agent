"""RAGDecider — semantic-based RAG retrieval decision, replacing hardcoded keywords."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

log = structlog.get_logger(__name__)

# Fallback keyword pattern (kept for fast-path check)
_RAG_KEYWORDS = re.compile(
    r"(健康|症状|疼痛|头痛|失眠|睡眠|血压|血糖|心率|体重|运动|饮食|营养|"
    r"药|用药|服药|剂量|副作用|中医|养生|穴位|食疗|调理|"
    r"疾病|感冒|发烧|咳嗽|过敏|炎症|焦虑|抑郁|压力|疲劳|"
    r"维生素|蛋白质|碳水|脂肪|膳食|忌口|禁忌|怎么办|怎么治|如何缓解)",
    re.IGNORECASE,
)


@dataclass
class RAGDecider:
    """Decides whether a user message needs RAG knowledge retrieval.

    Strategies (evaluated in order):
    1. Intent-based: certain intents always trigger retrieval.
    2. Keyword-based: fast regex fallback.
    3. LLM-based: optional semantic check (slower but smarter).
    """

    # Intents that always require RAG retrieval
    always_retrieve_intents: set[str] = field(default_factory=lambda: {"medication"})

    # Minimum message length to consider RAG (skip very short messages)
    min_message_length: int = 4

    async def should_retrieve(
        self,
        message: str,
        intent: str = "",
        *,
        enable_llm_check: bool = False,
    ) -> bool:
        """Determine if the message should trigger RAG retrieval.

        Args:
            message: The user's message text.
            intent: Classified intent (health/medication/insight/general).
            enable_llm_check: Whether to fall back to LLM-based semantic check.

        Returns:
            True if RAG retrieval should be performed.
        """
        if not message or len(message.strip()) < self.min_message_length:
            return False

        # Strategy 1: intent directly decides
        if intent and intent in self.always_retrieve_intents:
            log.debug("rag_decider_intent_match", intent=intent)
            return True

        # Strategy 2: keyword fast check (fallback)
        if _RAG_KEYWORDS.search(message):
            log.debug("rag_decider_keyword_match")
            return True

        # Strategy 3: optional LLM-based semantic check
        if enable_llm_check:
            return await self._llm_should_retrieve(message, intent)

        return False

    async def _llm_should_retrieve(self, message: str, intent: str) -> bool:
        """Use an LLM to decide if RAG retrieval is needed (semantic check).

        This is slower but handles cases where keywords miss the intent.
        Only called when enable_llm_check=True.
        """
        try:
            from app.llm.router import get_llm_router
            from app.utils.json_parser import parse_llm_json

            router = get_llm_router()
            prompt = (
                "判断以下用户消息是否需要从健康知识库检索参考资料。\n"
                "健康知识库包含：症状、用药、运动、饮食、中医养生等知识。\n\n"
                f'用户消息: "{message}"\n'
                f'用户意图: {intent or "未知"}\n\n'
                '只返回 JSON: {"need_retrieval": true/false}'
            )
            result = await router.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=20,
                response_format={"type": "json_object"},
            )
            data = parse_llm_json(result.content)
            need = bool(data.get("need_retrieval", False))
            log.debug("rag_decider_llm_check", need_retrieval=need)
            return need
        except Exception as e:
            log.warning("rag_decider_llm_check_failed", error=str(e))
            return False
