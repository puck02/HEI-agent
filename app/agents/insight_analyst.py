"""
Insight Analyst Agent — weekly/monthly trend analysis and anomaly detection.

Responsibilities:
- Generate weekly health insight reports
- Identify anomalous patterns in health metrics
- Provide science-backed explanations for trends using RAG
- Output must be compatible with Android InsightReport schema
"""

from __future__ import annotations

import json
from datetime import date

import structlog

from app.agents.state import AgentState
from app.llm.router import get_llm_router
from app.rag.engine import get_rag_engine

log = structlog.get_logger(__name__)

SYSTEM_PROMPT = """你是「洞察分析师」，HElDairy 的健康趋势分析助手。

核心原则：
1. 基于用户的历史健康数据，分析趋势和模式
2. 语气客观、温和，像一个值得信赖的健康顾问
3. 不做医疗诊断，发现异常时建议就医
4. 用简洁的语言总结，避免冗长
5. 建议要具体可执行，不要空泛"""


async def insight_analyst_node(state: AgentState) -> dict:
    """Main insight analyst node — handles trend/data analysis queries."""
    router = get_llm_router()
    rag_engine = get_rag_engine()

    user_msg = state.get("user_message", "")
    health_ctx = state.get("health_context", "")
    memory_ctx = state.get("memory_context", {})
    tool_outputs = state.get("tool_outputs", [])

    # RAG for scientific context
    rag_context = ""
    try:
        rag_context = await rag_engine.retrieve_as_context(
            user_msg, collections=["health", "tcm"], top_k=3
        )
    except Exception:
        pass

    context_parts = []
    if health_ctx:
        context_parts.append(f"【健康数据】\n{health_ctx}")
    if rag_context:
        context_parts.append(f"【参考知识】\n{rag_context}")
    if tool_outputs:
        context_parts.append(f"【工具结果】\n" + "\n".join(tool_outputs))

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if context_parts:
        messages.append({"role": "system", "content": "\n\n".join(context_parts)})

    history = memory_ctx.get("conversation_history", "")
    if history:
        messages.append({"role": "system", "content": f"对话历史：\n{history}"})

    messages.append({"role": "user", "content": user_msg})

    try:
        result = await router.chat(messages=messages, temperature=0.6, max_tokens=1024)
        return {
            "response": result.content,
            "model_used": result.model,
            "agent_used": "insight_analyst",
            "rag_context": rag_context,
        }
    except Exception as e:
        log.error("insight_analyst_error", error=str(e))
        return {
            "response": "洞察分析暂不可用，请稍后再试。",
            "agent_used": "insight_analyst",
        }


async def generate_weekly_insight(
    week_start: date,
    week_end: date,
    summary_7d: dict,
    summary_30d: dict | None = None,
    active_meds: list[str] | None = None,
) -> dict:
    """
    Generate weekly health insight report.
    Android-compatible output matching InsightReport.aiResultJson schema.
    """
    router = get_llm_router()
    rag = get_rag_engine()

    s7 = json.dumps(summary_7d, ensure_ascii=False, indent=2)
    s30 = json.dumps(summary_30d, ensure_ascii=False, indent=2) if summary_30d else "无"
    meds = ", ".join(active_meds) if active_meds else "无"

    # Get relevant knowledge for observed patterns
    query_hints = []
    if isinstance(summary_7d, dict):
        for key, val in summary_7d.items():
            if isinstance(val, (int, float)) and val >= 5:
                query_hints.append(key)
    rag_query = " ".join(query_hints) + " 健康趋势分析" if query_hints else "每周健康总结"

    rag_context = ""
    try:
        rag_context = await rag.retrieve_as_context(rag_query, collections=["health", "tcm"], top_k=3)
    except Exception:
        pass

    prompt = f"""{SYSTEM_PROMPT}

请为用户生成本周健康洞察。

统计周期：{week_start} ~ {week_end}

近 7 天摘要：
{s7}

近 30 天摘要：
{s30}

当前用药：{meds}

{f"参考知识：{rag_context}" if rag_context else ""}

严格按以下 JSON 格式输出：
{{
  "schemaVersion": 1,
  "weekStartDate": "{week_start}",
  "weekEndDate": "{week_end}",
  "summary": "2-4 句简短总结",
  "highlights": ["1-3 条本周值得注意的变化"],
  "suggestions": ["最多 3 条下周可执行建议"],
  "cautions": ["0-2 条就医提醒，可为空"],
  "confidence": "low|medium|high"
}}"""

    try:
        result = await router.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        data = json.loads(result.content)
        data["model"] = result.model
        return data
    except Exception as e:
        log.error("weekly_insight_failed", error=str(e))
        raise
