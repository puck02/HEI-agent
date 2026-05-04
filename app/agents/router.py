"""IntentRouter — classifies user intent for agent routing."""

from __future__ import annotations

import structlog

from app.llm.router import get_llm_router
from app.utils.json_parser import parse_llm_json

log = structlog.get_logger(__name__)

_VALID_INTENTS = frozenset({"health", "medication", "insight", "general"})


class IntentRouter:
    """Classifies user messages into intents for sub-agent routing."""

    _PROMPT_TEMPLATE = (
        '请分析以下用户消息的意图，返回一个 JSON：\n\n'
        '用户消息: "{message}"\n\n'
        '意图分类：\n'
        '- health: 健康相关咨询（症状、睡眠、运动、饮食、情绪、日报建议等）\n'
        '- medication: 用药相关（药品查询、用药记录、药品说明、剂量等）\n'
        '- insight: 数据分析相关（趋势、洞察、统计、报告、对比等）\n'
        '- general: 其他一般对话（问候、闲聊、设置等）\n\n'
        '只返回 JSON：{{"intent": "health|medication|insight|general"}}'
    )

    async def classify_intent(self, user_message: str) -> str:
        """Return one of: health, medication, insight, general."""
        router = get_llm_router()
        prompt = self._PROMPT_TEMPLATE.format(message=user_message)

        try:
            result = await router.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=50,
                response_format={"type": "json_object"},
            )
            data = parse_llm_json(result.content)
            intent = data.get("intent", "general")
            if intent not in _VALID_INTENTS:
                intent = "general"
        except Exception as e:
            log.warning("intent_classification_failed", error=str(e), fallback="general")
            intent = "general"

        log.info("intent_classified", intent=intent, message=user_message[:50])
        return intent
