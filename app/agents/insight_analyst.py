"""
Insight Analyst Agent — weekly/monthly trend analysis and anomaly detection.

Architecture: ReAct (Reason + Act) pattern with tool calling.

Responsibilities:
- Generate weekly health insight reports
- Identify anomalous patterns in health metrics
- Use tools to analyze trends, generate summaries, compare periods
- Provide science-backed explanations for trends using RAG
- Output must be compatible with Android InsightReport schema
"""

from __future__ import annotations

import json
from datetime import date

import structlog

from app.agents.state import AgentState
from app.agents.tools import (
    INSIGHT_TOOLS,
    query_health_data,
    analyze_health_trend,
    generate_weekly_summary,
    compare_periods,
)
from app.utils.json_parser import parse_llm_json
from app.llm.router import get_llm_router
from app.rag.engine import get_rag_engine

log = structlog.get_logger(__name__)

SYSTEM_PROMPT = """你是「Kitty 洞察分析师 🎀」，Hello Kitty 人设的专业健康趋势分析助手。

核心人设：
- 以 Hello Kitty 可爱的风格和用户交流，同时保持数据分析的专业性
- 你非常了解用户的健康状况和历史数据

核心原则：
1. 基于用户的真实历史健康数据，分析趋势和模式
2. 语气温柔可爱但客观专业，像一个值得信赖的健康顾问
3. 发现异常时温柔提醒建议就医
4. 用简洁的语言总结，避免冗长
5. 建议要具体可执行

你可以使用以下工具（ReAct 模式）：
- query_health_data: 查询具体健康数据
- analyze_health_trend: 分析某项指标的趋势
- generate_weekly_summary: 生成周报摘要
- compare_periods: 对比两个时间段的数据"""


# ── ReAct Tool Execution ─────────────────────────────────────────────────────

REACT_PROMPT = """你是洞察分析师，使用 ReAct 模式分析用户健康趋势。

可用工具：
{tools_desc}

用户问题：{user_message}

上下文信息：
{context}

请按以下格式思考和回答：

Thought: [分析问题，决定需要什么数据]
Action: [工具名称] 或 None
Action Input: {{"参数": "值"}} 或 None
Observation: [等待工具结果]
... (可重复)
Final Answer: [最终分析报告，客观、温和、有具体建议]

注意：
- 如果需要分析趋势，使用 analyze_health_trend
- 如果用户要看周报，使用 generate_weekly_summary
- 最多调用 3 次工具
- 必须以 Final Answer 结尾"""


async def execute_insight_react_loop(
    user_message: str,
    context: str,
    user_id: str,
    max_iterations: int = 3,
) -> tuple[str, list[dict], list[str]]:
    """Execute ReAct loop for insight analyst."""
    router = get_llm_router()

    tools_desc = """
- query_health_data(user_id, data_type, days): 查询健康数据
- analyze_health_trend(user_id, metric, period_days): 分析趋势
- generate_weekly_summary(user_id): 生成周报摘要
- compare_periods(user_id, metric, period1_start, period2_start, duration_days): 对比周期"""

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
        log.debug("insight_react_iteration", iteration=iteration, response=response_text[:200])

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

                observation = await execute_insight_tool(action_name, action_input_str, user_id)
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
                log.warning("insight_react_parse_error", error=str(e))
                react_steps.append({"iteration": iteration, "type": "error", "error": str(e)})
                return response_text, react_steps, tools_called
        else:
            react_steps.append({"iteration": iteration, "type": "thought", "content": response_text})
            conversation.append({"role": "assistant", "content": response_text})
            conversation.append({"role": "user", "content": "请继续，给出 Action 或 Final Answer。"})

    return response_text, react_steps, tools_called


async def execute_insight_tool(action_name: str, input_str: str, user_id: str) -> str:
    """Execute an insight tool."""
    try:
        if input_str.startswith("{"):
            inputs = parse_llm_json(input_str)
        else:
            inputs = {"metric": input_str}

        inputs["user_id"] = user_id

        if action_name == "query_health_data":
            return query_health_data.invoke(inputs)
        elif action_name == "analyze_health_trend":
            return analyze_health_trend.invoke(inputs)
        elif action_name == "generate_weekly_summary":
            return generate_weekly_summary.invoke(inputs)
        elif action_name == "compare_periods":
            return compare_periods.invoke(inputs)
        else:
            return f"未知工具: {action_name}"
    except Exception as e:
        log.warning("insight_tool_error", tool=action_name, error=str(e))
        return f"工具执行出错: {str(e)}"


async def insight_analyst_node(state: AgentState) -> dict:
    """Main insight analyst node with ReAct pattern."""
    rag_engine = get_rag_engine()

    user_msg = state.get("user_message", "")
    user_id = state.get("user_id", "")
    health_ctx = state.get("health_context", "")
    memory_ctx = state.get("memory_context", {})

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

    history = memory_ctx.get("conversation_history", "")
    if history:
        context_parts.append(f"【对话历史】\n{history}")

    full_context = "\n\n".join(context_parts) if context_parts else "暂无上下文"

    try:
        final_answer, react_steps, tools_called = await execute_insight_react_loop(
            user_message=user_msg,
            context=full_context,
            user_id=user_id,
            max_iterations=3,
        )

        log.info("insight_analyst_react_complete", steps=len(react_steps), tools=tools_called)

        return {
            "response": final_answer,
            "agent_used": "insight_analyst",
            "rag_context": rag_context,
            "react_steps": react_steps,
            "tools_called": tools_called,
        }
    except Exception as e:
        log.error("insight_analyst_error", error=str(e))
        return {
            "response": "洞察分析暂不可用，请稍后再试。",
            "agent_used": "insight_analyst",
            "react_steps": [],
            "tools_called": [],
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
        data = parse_llm_json(result.content)
        data["model"] = result.model
        return data
    except Exception as e:
        log.error("weekly_insight_failed", error=str(e), raw_content=result.content[:200] if 'result' in dir() else None)
        raise
