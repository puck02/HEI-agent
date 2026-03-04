"""
Medication Agent — NLP parsing, drug info queries, interaction checks.

Responsibilities:
- Parse natural language medication events into structured actions
- Answer medication-related questions using RAG knowledge base
- Generate medication info summaries from text/OCR
- Safety guardrail: NEVER suggest changing medication or dosage
"""

from __future__ import annotations

import structlog

from app.agents.state import AgentState
from app.utils.json_parser import parse_llm_json
from app.llm.router import get_llm_router
from app.rag.engine import get_rag_engine

log = structlog.get_logger(__name__)

SYSTEM_PROMPT = """你是「用药管家」，HElDairy 的用药管理助手。

核心原则：
1. 你帮助用户记录和管理用药信息，但绝不建议更改药物或剂量
2. 你可以整理药品说明书信息（用法用量、注意事项、不良反应）
3. 发现潜在的用药冲突提醒用户咨询医生，但不做判断
4. 语气专业但温和
5. 仅为信息整理，不构成医疗建议"""


async def medication_agent_node(state: AgentState) -> dict:
    """Main medication agent node — handles medication-related queries."""
    router = get_llm_router()
    rag_engine = get_rag_engine()

    user_msg = state.get("user_message", "")
    med_ctx = state.get("medication_context", "")
    memory_ctx = state.get("memory_context", {})

    # RAG: medication knowledge
    rag_context = ""
    try:
        rag_context = await rag_engine.retrieve_as_context(
            user_msg, collections=["medication"], top_k=3
        )
    except Exception as e:
        log.warning("med_rag_failed", error=str(e))

    context_parts = []
    if med_ctx:
        context_parts.append(f"【当前用药】\n{med_ctx}")
    if rag_context:
        context_parts.append(f"【药品知识】\n{rag_context}")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if context_parts:
        messages.append({
            "role": "system",
            "content": "\n\n".join(context_parts),
        })

    history = memory_ctx.get("conversation_history", "")
    if history:
        messages.append({"role": "system", "content": f"对话历史：\n{history}"})

    messages.append({"role": "user", "content": user_msg})

    try:
        result = await router.chat(messages=messages, temperature=0.5, max_tokens=1024)
        return {
            "response": result.content,
            "model_used": result.model,
            "agent_used": "medication_agent",
            "rag_context": rag_context,
        }
    except Exception as e:
        log.error("medication_agent_error", error=str(e))
        return {
            "response": "用药管家暂时无法回答，请稍后再试。",
            "agent_used": "medication_agent",
        }


async def parse_medication_nlp(
    raw_text: str,
    current_meds: list[str],
    active_courses: list[dict] | None = None,
) -> dict:
    """
    Parse natural language medication event into structured actions.
    Android-compatible output: {mentioned_meds, actions, questions}
    """
    router = get_llm_router()

    meds_str = ", ".join(current_meds) if current_meds else "无"
    courses_str = json.dumps(active_courses, ensure_ascii=False) if active_courses else "无"

    prompt = f"""{SYSTEM_PROMPT}

用户的自然语言输入：
"{raw_text}"

当前药品库：{meds_str}
当前活跃疗程：{courses_str}

请分析用户意图并返回结构化 JSON：
{{
  "mentioned_meds": [
    {{"name": "药名", "in_library": true/false}}
  ],
  "actions": [
    {{
      "action_type": "add_med|start_course|pause_course|end_course|update_course|noop",
      "med_name": "药名",
      "course_fields": {{
        "startDate": "YYYY-MM-DD (可选)",
        "endDate": "YYYY-MM-DD (可选)",
        "status": "active|paused|ended (可选)",
        "frequencyText": "频率 (可选)",
        "doseText": "剂量 (可选)",
        "timeHints": "时间 (可选)"
      }}
    }}
  ],
  "questions": [
    {{"text": "需要澄清的问题", "options": ["选项1", "选项2"]}}
  ]
}}

要求：
- 新药自动建议 add_med
- questions 最多 2 个，优先选择题
- 不确定的信息用 questions 澄清，不要猜"""

    try:
        result = await router.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        data = parse_llm_json(result.content)
        data["model"] = result.model
        return data
    except Exception as e:
        log.error("med_nlp_parse_failed", error=str(e), raw_content=result.content[:200] if 'result' in dir() else None)
        raise


async def generate_med_info_summary(text: str, med_name: str | None = None) -> dict:
    """
    Extract medication info summary from text (e.g., drug label OCR).
    Returns: {name_candidates, dosage_summary, cautions_summary, adverse_summary}
    """
    router = get_llm_router()

    prompt = f"""{SYSTEM_PROMPT}

请从以下文本中提取药品信息，整理为结构化摘要。

文本内容：
{text}

{f"疑似药名：{med_name}" if med_name else ""}

输出 JSON：
{{
  "name_candidates": ["可能的药品名称"],
  "dosage_summary": "用法用量摘要",
  "cautions_summary": "注意事项摘要",
  "adverse_summary": "不良反应摘要"
}}

说明：仅为说明书信息整理，不构成医疗建议。"""

    try:
        result = await router.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        data = parse_llm_json(result.content)
        data["model"] = result.model
        return data
    except Exception as e:
        log.error("med_info_summary_failed", error=str(e), raw_content=result.content[:200] if 'result' in dir() else None)
        raise
