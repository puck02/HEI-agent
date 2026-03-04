"""
Health Advisor Agent — daily advice, adaptive follow-ups, health Q&A.

Responsibilities:
- Generate daily lifestyle advice based on today's health entries
- Produce adaptive follow-up questions triggered by symptom severity
- Answer general health & wellness questions using RAG knowledge
- Maintain the warm "生活管家" tone — never diagnose, never suggest medication changes
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from app.agents.state import AgentState
from app.llm.router import get_llm_router
from app.rag.engine import get_rag_engine

log = structlog.get_logger(__name__)

SYSTEM_PROMPT = """你是「健康小助手」，一个温柔、理性的 AI 私人健康生活管家。

核心原则：
1. 你只提供生活方式建议（饮食、运动、睡眠、情绪管理等），绝不做医疗诊断
2. 你绝不建议用户更改药物剂量或停药，用药问题请咨询医生
3. 语气温柔关心，像一个贴心的朋友，不夸张、不恐吓
4. 如果发现需要就医的信号，温柔提醒"如出现以下情况请及时就医"
5. 回答基于用户的实际健康数据和科学的健康知识

你可以使用以下信息：
- 用户今日健康数据和历史趋势
- 健康知识库中的参考信息
- 用户的长期健康记忆和偏好"""


async def health_advisor_node(state: AgentState) -> dict:
    """
    Main health advisor agent node.
    Processes user message with health context and RAG knowledge.
    """
    router = get_llm_router()
    rag_engine = get_rag_engine()

    user_msg = state.get("user_message", "")
    health_ctx = state.get("health_context", "")
    med_ctx = state.get("medication_context", "")
    memory_ctx = state.get("memory_context", {})
    tool_outputs = state.get("tool_outputs", [])

    # Retrieve relevant knowledge from RAG
    rag_context = ""
    try:
        rag_context = await rag_engine.retrieve_as_context(
            user_msg,
            collections=["health", "tcm"],
            top_k=3,
        )
    except Exception as e:
        log.warning("rag_retrieval_failed", error=str(e))

    # Build context block
    context_parts = []
    if health_ctx:
        context_parts.append(f"【用户健康数据】\n{health_ctx}")
    if med_ctx:
        context_parts.append(f"【当前用药情况】\n{med_ctx}")
    if memory_ctx.get("relevant_memories"):
        mem_text = "\n".join(f"- {m}" for m in memory_ctx["relevant_memories"])
        context_parts.append(f"【用户记忆】\n{mem_text}")
    if rag_context:
        context_parts.append(f"【参考知识】\n{rag_context}")
    if tool_outputs:
        tool_text = "\n".join(tool_outputs)
        context_parts.append(f"【工具输出】\n{tool_text}")

    full_context = "\n\n".join(context_parts)

    # Build messages
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add conversation history
    history = memory_ctx.get("conversation_history", "")
    if history:
        messages.append({
            "role": "system",
            "content": f"对话历史：\n{history}",
        })

    if full_context:
        messages.append({
            "role": "system",
            "content": f"可用上下文：\n{full_context}",
        })

    messages.append({"role": "user", "content": user_msg})

    # Call LLM
    try:
        result = await router.chat(
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
        )
        return {
            "response": result.content,
            "model_used": result.model,
            "agent_used": "health_advisor",
            "rag_context": rag_context,
        }
    except Exception as e:
        log.error("health_advisor_llm_error", error=str(e))
        return {
            "response": "抱歉，健康顾问暂时无法回答。请稍后再试。",
            "agent_used": "health_advisor",
        }


async def generate_daily_advice(
    today_answers: dict[str, Any],
    summary_7d: dict | None = None,
    active_meds: list[str] | None = None,
    adherence_hint: str | None = None,
) -> dict:
    """
    Generate daily lifestyle advice — Android-compatible JSON output.
    Returns: {observations, actions, tomorrow_focus, red_flags}
    """
    router = get_llm_router()
    rag = get_rag_engine()

    # Build prompt
    answers_text = json.dumps(today_answers, ensure_ascii=False, indent=2)
    summary_text = json.dumps(summary_7d, ensure_ascii=False, indent=2) if summary_7d else "无"

    # Get relevant health knowledge
    symptoms = []
    for key, val in today_answers.items():
        if isinstance(val, (int, float)) and val >= 5:
            symptoms.append(key)
    symptom_query = " ".join(symptoms) + " 生活调理建议" if symptoms else "日常健康保养建议"

    rag_context = ""
    try:
        rag_context = await rag.retrieve_as_context(symptom_query, collections=["health", "tcm"], top_k=3)
    except Exception:
        pass

    context = f"""今日健康数据：
{answers_text}

最近 7 天摘要：
{summary_text}"""

    if active_meds:
        context += f"\n\n当前用药：{', '.join(active_meds)}"
    if adherence_hint:
        context += f"\n用药情况：{adherence_hint}"
    if rag_context:
        context += f"\n\n参考知识：\n{rag_context}"

    prompt = f"""{SYSTEM_PROMPT}

请基于以下信息，生成今日生活建议。

{context}

请严格按以下 JSON 格式输出（不要输出其他内容）：
{{
  "observations": ["今天的观察，1-3 条"],
  "actions": ["具体建议，最多 3 条"],
  "tomorrow_focus": ["明天重点关注，1-2 条"],
  "red_flags": ["如出现以下情况请就医，0-2 条，可为空"]
}}"""

    try:
        result = await router.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        advice = json.loads(result.content)
        advice["model"] = result.model
        return advice
    except Exception as e:
        log.error("daily_advice_generation_failed", error=str(e))
        raise


async def generate_follow_up_questions(
    today_answers: dict[str, Any],
    summary_7d: dict | None = None,
    triggered_symptoms: list[str] | None = None,
) -> dict:
    """
    Generate adaptive follow-up questions — Android-compatible JSON output.
    Returns: {questions: [{text, type, options}]}
    """
    router = get_llm_router()

    answers_text = json.dumps(today_answers, ensure_ascii=False, indent=2)
    summary_text = json.dumps(summary_7d, ensure_ascii=False, indent=2) if summary_7d else "无"
    triggered = ", ".join(triggered_symptoms) if triggered_symptoms else "无特别触发"

    prompt = f"""{SYSTEM_PROMPT}

用户今日健康数据：
{answers_text}

最近 7 天摘要：
{summary_text}

触发追问的症状：{triggered}

请生成 1-2 个补充追问问题，帮助更好地了解用户状况。

严格按以下 JSON 格式输出：
{{
  "questions": [
    {{
      "text": "问题文本",
      "type": "choice 或 slider",
      "options": ["选项1", "选项2", "选项3"]
    }}
  ]
}}

要求：
- 最多 2 个问题
- 不允许诊断性问题
- 不允许开放式长问
- 选择题优先"""

    try:
        result = await router.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=500,
            response_format={"type": "json_object"},
        )
        data = json.loads(result.content)
        data["model"] = result.model
        return data
    except Exception as e:
        log.error("follow_up_generation_failed", error=str(e))
        raise
