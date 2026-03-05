"""
Medication Agent — NLP parsing, drug info queries, interaction checks.

Architecture: ReAct (Reason + Act) pattern with tool calling.

Responsibilities:
- Parse natural language medication events into structured actions
- Answer medication-related questions using RAG knowledge base
- Generate medication info summaries from text/OCR
- Use tools to query drug info, check interactions, view records
- Safety guardrail: NEVER suggest changing medication or dosage
"""

from __future__ import annotations

import json

import structlog

from app.agents.state import AgentState
from app.agents.tools import (
    MEDICATION_TOOLS,
    search_medication_info,
    check_drug_interaction,
    query_medication_records,
    query_health_data,
)
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
5. 仅为信息整理，不构成医疗建议

你可以使用以下工具（ReAct 模式）：
- search_medication_info: 查询药品详细信息（用法、禁忌、副作用）
- check_drug_interaction: 检查两种药物的相互作用
- query_medication_records: 查询用户用药记录
- query_health_data: 查询用户健康数据（辅助判断）"""


# ── ReAct Tool Execution ─────────────────────────────────────────────────────

REACT_PROMPT = """你是用药管家，使用 ReAct 模式回答药物相关问题。

可用工具：
{tools_desc}

用户问题：{user_message}

上下文信息：
{context}

请按以下格式思考和回答：

Thought: [分析问题，决定是否需要工具]
Action: [工具名称] 或 None
Action Input: {{"参数": "值"}} 或 None
Observation: [等待工具结果]
... (可重复)
Final Answer: [最终回答，专业、温和、不做医疗建议]

注意：
- 如果需要查询药品信息，使用 search_medication_info
- 如果用户问两种药能否一起吃，使用 check_drug_interaction
- 最多调用 3 次工具
- 必须以 Final Answer 结尾"""


async def execute_med_react_loop(
    user_message: str,
    context: str,
    user_id: str,
    max_iterations: int = 3,
) -> tuple[str, list[dict], list[str]]:
    """Execute ReAct loop for medication agent."""
    router = get_llm_router()

    tools_desc = """
- search_medication_info(drug_name): 查询药品信息
- check_drug_interaction(drug1, drug2): 检查药物相互作用
- query_medication_records(user_id, days): 查询用户用药记录
- query_health_data(user_id, data_type, days): 查询健康数据"""

    prompt = REACT_PROMPT.format(
        tools_desc=tools_desc,
        user_message=user_message,
        context=context,
    )

    react_steps = []
    tools_called = []
    conversation = [{"role": "user", "content": prompt}]

    for iteration in range(max_iterations):
        result = await router.chat(
            messages=conversation,
            temperature=0.3,
            max_tokens=800,
        )

        response_text = result.content
        log.debug("med_react_iteration", iteration=iteration, response=response_text[:200])

        if "Final Answer:" in response_text:
            final_answer = response_text.split("Final Answer:")[-1].strip()
            react_steps.append({"iteration": iteration, "type": "final", "content": final_answer})
            return final_answer, react_steps, tools_called

        if "Action:" in response_text and "Action Input:" in response_text:
            try:
                action_line = [l for l in response_text.split("\n") if l.strip().startswith("Action:")][0]
                action_name = action_line.split("Action:")[-1].strip()

                input_start = response_text.find("Action Input:")
                input_end = response_text.find("\n", input_start + 14)
                if input_end == -1:
                    input_end = len(response_text)
                action_input_str = response_text[input_start + 13:input_end].strip()

                observation = await execute_med_tool(action_name, action_input_str, user_id)
                tools_called.append(action_name)

                react_steps.append({
                    "iteration": iteration,
                    "type": "action",
                    "action": action_name,
                    "input": action_input_str,
                    "observation": observation,
                })

                conversation.append({"role": "assistant", "content": response_text})
                conversation.append({"role": "user", "content": f"Observation: {observation}\n\n请继续思考或给出 Final Answer。"})

            except Exception as e:
                log.warning("med_react_parse_error", error=str(e))
                react_steps.append({"iteration": iteration, "type": "error", "error": str(e)})
                return response_text, react_steps, tools_called
        else:
            react_steps.append({"iteration": iteration, "type": "thought", "content": response_text})
            conversation.append({"role": "assistant", "content": response_text})
            conversation.append({"role": "user", "content": "请继续，给出 Action 或 Final Answer。"})

    return response_text, react_steps, tools_called


async def execute_med_tool(action_name: str, input_str: str, user_id: str) -> str:
    """Execute a medication tool."""
    try:
        if input_str.startswith("{"):
            inputs = parse_llm_json(input_str)
        else:
            inputs = {"drug_name": input_str}

        if action_name == "search_medication_info":
            return search_medication_info.invoke(inputs)
        elif action_name == "check_drug_interaction":
            return check_drug_interaction.invoke(inputs)
        elif action_name == "query_medication_records":
            inputs["user_id"] = user_id
            return query_medication_records.invoke(inputs)
        elif action_name == "query_health_data":
            inputs["user_id"] = user_id
            return query_health_data.invoke(inputs)
        else:
            return f"未知工具: {action_name}"
    except Exception as e:
        log.warning("med_tool_error", tool=action_name, error=str(e))
        return f"工具执行出错: {str(e)}"


async def medication_agent_node(state: AgentState) -> dict:
    """Main medication agent node with ReAct pattern."""
    rag_engine = get_rag_engine()

    user_msg = state.get("user_message", "")
    user_id = state.get("user_id", "")
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

    history = memory_ctx.get("conversation_history", "")
    if history:
        context_parts.append(f"【对话历史】\n{history}")

    full_context = "\n\n".join(context_parts) if context_parts else "暂无上下文"

    try:
        final_answer, react_steps, tools_called = await execute_med_react_loop(
            user_message=user_msg,
            context=full_context,
            user_id=user_id,
            max_iterations=3,
        )

        log.info("medication_agent_react_complete", steps=len(react_steps), tools=tools_called)

        return {
            "response": final_answer,
            "agent_used": "medication_agent",
            "rag_context": rag_context,
            "react_steps": react_steps,
            "tools_called": tools_called,
        }
    except Exception as e:
        log.error("medication_agent_error", error=str(e))
        return {
            "response": "用药管家暂时无法回答，请稍后再试。",
            "agent_used": "medication_agent",
            "react_steps": [],
            "tools_called": [],
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
