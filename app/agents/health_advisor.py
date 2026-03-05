"""
Health Advisor Agent — daily advice, adaptive follow-ups, health Q&A.

Architecture: ReAct (Reason + Act) pattern with tool calling.

Responsibilities:
- Generate daily lifestyle advice based on today's health entries
- Produce adaptive follow-up questions triggered by symptom severity
- Answer general health & wellness questions using RAG knowledge
- Use tools to query user health data, calculate BMI, etc.
- Maintain the warm "生活管家" tone — never diagnose, never suggest medication changes
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from app.agents.state import AgentState
from app.agents.tools import HEALTH_TOOLS, query_health_data, calculate_bmi, get_weather, calculate_water_intake
from app.utils.json_parser import parse_llm_json
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

你可以使用以下工具来获取信息（ReAct 模式）：
- query_health_data: 查询用户最近的健康数据（血压、血糖、睡眠、体重等）
- calculate_bmi: 根据体重和身高计算 BMI
- get_weather: 获取天气信息（影响运动建议）
- calculate_water_intake: 计算建议饮水量

思考过程（ReAct）：
1. Thought: 分析用户问题，决定是否需要查询数据
2. Action: 如需要，调用工具获取数据
3. Observation: 观察工具返回的结果
4. ... 重复直到有足够信息
5. Final Answer: 基于所有信息生成个性化建议"""


# ── ReAct Tool Execution ─────────────────────────────────────────────────────

REACT_PROMPT = """你是一个健康助手，使用 ReAct 模式回答问题。

可用工具：
{tools_desc}

用户问题：{user_message}

上下文信息：
{context}

请按以下格式思考和回答：

Thought: [分析问题，决定是否需要工具]
Action: [工具名称] 或 None
Action Input: {{"参数": "值"}} 或 None
Observation: [等待工具结果，我会填入]
... (可重复 Thought/Action/Observation)
Final Answer: [最终回答，温柔、关心、基于数据]

注意：
- 如果问题很简单不需要工具，直接给出 Final Answer
- 最多调用 3 次工具
- 必须以 Final Answer 结尾"""


async def execute_react_loop(
    user_message: str,
    context: str,
    user_id: str,
    max_iterations: int = 3,
) -> tuple[str, list[dict], list[str]]:
    """
    Execute ReAct loop: Thought → Action → Observation → ... → Final Answer

    Returns:
        (final_answer, react_steps, tools_called)
    """
    router = get_llm_router()

    tools_desc = """
- query_health_data(user_id, data_type, days): 查询健康数据
  - data_type: blood_pressure/blood_sugar/sleep/weight/heart_rate/mood
  - days: 查询天数，默认7
- calculate_bmi(weight_kg, height_m): 计算BMI
- get_weather(city): 获取天气
- calculate_water_intake(weight_kg, exercise_minutes): 计算饮水量"""

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
        log.debug("react_iteration", iteration=iteration, response=response_text[:200])

        # Parse the response
        if "Final Answer:" in response_text:
            # Extract final answer
            final_answer = response_text.split("Final Answer:")[-1].strip()
            react_steps.append({
                "iteration": iteration,
                "type": "final",
                "content": final_answer,
            })
            return final_answer, react_steps, tools_called

        # Check for Action
        if "Action:" in response_text and "Action Input:" in response_text:
            try:
                # Parse action and input
                action_line = [l for l in response_text.split("\n") if l.strip().startswith("Action:")][0]
                action_name = action_line.split("Action:")[-1].strip()

                input_start = response_text.find("Action Input:")
                input_end = response_text.find("\n", input_start + 14)
                if input_end == -1:
                    input_end = len(response_text)
                action_input_str = response_text[input_start + 13:input_end].strip()

                # Execute tool
                observation = await execute_tool(action_name, action_input_str, user_id)
                tools_called.append(action_name)

                react_steps.append({
                    "iteration": iteration,
                    "type": "action",
                    "action": action_name,
                    "input": action_input_str,
                    "observation": observation,
                })

                # Add observation to conversation
                conversation.append({"role": "assistant", "content": response_text})
                conversation.append({"role": "user", "content": f"Observation: {observation}\n\n请继续思考或给出 Final Answer。"})

            except Exception as e:
                log.warning("react_action_parse_error", error=str(e))
                # Fallback: treat response as final answer
                react_steps.append({"iteration": iteration, "type": "error", "error": str(e)})
                return response_text, react_steps, tools_called
        else:
            # No action, treat as thinking or partial response
            react_steps.append({
                "iteration": iteration,
                "type": "thought",
                "content": response_text,
            })
            # Continue conversation
            conversation.append({"role": "assistant", "content": response_text})
            conversation.append({"role": "user", "content": "请继续，给出 Action 或 Final Answer。"})

    # Max iterations reached, extract whatever we have
    return response_text, react_steps, tools_called


async def execute_tool(action_name: str, input_str: str, user_id: str) -> str:
    """Execute a tool and return the observation."""
    try:
        # Parse input (handle both JSON and simple string)
        if input_str.startswith("{"):
            inputs = parse_llm_json(input_str)
        else:
            inputs = {"query": input_str}

        # Inject user_id if needed
        if "user_id" in inputs or action_name in ["query_health_data", "query_medication_records"]:
            inputs["user_id"] = user_id

        # Execute tool
        if action_name == "query_health_data":
            return query_health_data.invoke(inputs)
        elif action_name == "calculate_bmi":
            return calculate_bmi.invoke(inputs)
        elif action_name == "get_weather":
            return get_weather.invoke(inputs)
        elif action_name == "calculate_water_intake":
            return calculate_water_intake.invoke(inputs)
        else:
            return f"未知工具: {action_name}"

    except Exception as e:
        log.warning("tool_execution_error", tool=action_name, error=str(e))
        return f"工具执行出错: {str(e)}"


# ── Main Agent Node ──────────────────────────────────────────────────────────


# ── Main Agent Node ──────────────────────────────────────────────────────────


async def health_advisor_node(state: AgentState) -> dict:
    """
    Main health advisor agent node with ReAct pattern.
    Processes user message with health context, RAG knowledge, and tool execution.
    """
    rag_engine = get_rag_engine()

    user_msg = state.get("user_message", "")
    user_id = state.get("user_id", "")
    health_ctx = state.get("health_context", "")
    med_ctx = state.get("medication_context", "")
    memory_ctx = state.get("memory_context", {})

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

    history = memory_ctx.get("conversation_history", "")
    if history:
        context_parts.append(f"【对话历史】\n{history}")

    full_context = "\n\n".join(context_parts) if context_parts else "暂无上下文"

    # Execute ReAct loop
    try:
        final_answer, react_steps, tools_called = await execute_react_loop(
            user_message=user_msg,
            context=full_context,
            user_id=user_id,
            max_iterations=3,
        )

        log.info(
            "health_advisor_react_complete",
            steps=len(react_steps),
            tools=tools_called,
        )

        return {
            "response": final_answer,
            "agent_used": "health_advisor",
            "rag_context": rag_context,
            "react_steps": react_steps,
            "tools_called": tools_called,
        }
    except Exception as e:
        log.error("health_advisor_react_error", error=str(e))
        # Fallback to simple response
        return {
            "response": "抱歉，健康顾问暂时无法回答。请稍后再试。",
            "agent_used": "health_advisor",
            "react_steps": [],
            "tools_called": [],
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
        advice = parse_llm_json(result.content)
        advice["model"] = result.model
        return advice
    except Exception as e:
        log.error("daily_advice_generation_failed", error=str(e), raw_content=result.content[:200] if 'result' in dir() else None)
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
        data = parse_llm_json(result.content)
        data["model"] = result.model
        return data
    except Exception as e:
        log.error("follow_up_generation_failed", error=str(e), raw_content=result.content[:200] if 'result' in dir() else None)
        raise
