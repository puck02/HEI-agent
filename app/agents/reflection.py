"""
Reflection Node — Self-evaluation and quality assurance for agent responses.

The Reflection node evaluates generated responses against quality criteria:
1. Completeness: Did the response answer the user's question?
2. Safety Boundary: No medical diagnosis, no medication change suggestions
3. Tone: Warm, friendly, not alarming
4. Accuracy: Based on actual data, not hallucinated
5. Personalization: Uses user's actual health context

If the response fails quality checks, it generates an improved version.
Maximum 2 retries to prevent infinite loops.
"""

from __future__ import annotations

import structlog

from app.agents.state import AgentState
from app.llm.router import get_llm_router
from app.utils.json_parser import parse_llm_json

log = structlog.get_logger(__name__)

# ── Reflection Prompt ────────────────────────────────────────────────────────

REFLECTION_PROMPT = """你是一个严格的健康回答质量审核员。请评估以下 AI 健康助手的回答质量。

【用户问题】
{user_message}

【使用的 Agent】
{agent_used}

【AI 回答】
{response}

请从以下 5 个维度评估（每项 0-2 分）：

1. **完整性** (0-2分)
   - 2分: 完整回答了用户的问题
   - 1分: 部分回答，有遗漏
   - 0分: 没有回答核心问题

2. **安全边界** (0-2分)
   - 2分: 严格遵守边界，不做诊断、不建议改药
   - 1分: 有轻微越界倾向但可接受
   - 0分: 明显越界（做了诊断或建议改药）

3. **语气友好度** (0-2分)
   - 2分: 温柔、关心、不恐吓
   - 1分: 语气中性
   - 0分: 冷淡、恐吓、生硬

4. **信息准确性** (0-2分)
   - 2分: 基于数据和知识，无明显错误
   - 1分: 基本准确，有小瑕疵
   - 0分: 有明显错误或编造信息

5. **个性化程度** (0-2分)
   - 2分: 结合了用户的实际情况给出建议
   - 1分: 部分个性化
   - 0分: 完全泛泛而谈

请返回 JSON 格式：
{{
    "scores": {{
        "completeness": 0-2,
        "safety_boundary": 0-2,
        "tone": 0-2,
        "accuracy": 0-2,
        "personalization": 0-2
    }},
    "total_score": 0-10,
    "issues": ["问题1", "问题2"],
    "should_retry": true/false,
    "improved_response": "如果 should_retry=true，提供改进后的完整回答；否则为 null"
}}

评判标准：
- 总分 >= 8: 通过，should_retry = false
- 总分 < 8: 需要改进，should_retry = true，并提供改进版本
- 如果安全边界得分为 0: 必须重试"""


# ── Reflection Node ──────────────────────────────────────────────────────────


async def reflection_node(state: AgentState) -> dict:
    """
    Reflection node: evaluate response quality and retry if needed.

    Max 2 retries to prevent infinite loops.
    """
    router = get_llm_router()

    user_message = state.get("user_message", "")
    response = state.get("response", "")
    agent_used = state.get("agent_used", "unknown")
    retry_count = state.get("reflection_retry_count", 0)

    # Skip reflection for empty responses
    if not response:
        log.warning("reflection_skip_empty_response")
        return {"reflection_passed": True}

    # Max 2 retries
    if retry_count >= 2:
        log.info("reflection_max_retries_reached", retry_count=retry_count)
        return {"reflection_passed": True}

    # Skip reflection for general/greeting responses (less critical)
    if agent_used == "general" and len(response) < 50:
        log.debug("reflection_skip_simple_general")
        return {"reflection_passed": True}

    prompt = REFLECTION_PROMPT.format(
        user_message=user_message,
        agent_used=agent_used,
        response=response,
    )

    try:
        result = await router.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )

        reflection = parse_llm_json(result.content)

        scores = reflection.get("scores", {})
        total_score = reflection.get("total_score", 10)
        issues = reflection.get("issues", [])
        should_retry = reflection.get("should_retry", False)
        improved_response = reflection.get("improved_response")

        log.info(
            "reflection_result",
            total_score=total_score,
            scores=scores,
            issues=issues,
            should_retry=should_retry,
            retry_count=retry_count,
        )

        # Safety boundary violation — must retry
        if scores.get("safety_boundary", 2) == 0:
            should_retry = True
            log.warning("reflection_safety_violation", issues=issues)

        if should_retry and improved_response:
            return {
                "response": improved_response,
                "reflection_retry_count": retry_count + 1,
                "reflection_passed": False,
                "reflection_scores": scores,
            }

        return {
            "reflection_passed": True,
            "reflection_scores": scores,
        }

    except Exception as e:
        log.error("reflection_error", error=str(e))
        # On error, pass through (fail-open)
        return {"reflection_passed": True}


def should_retry_reflection(state: AgentState) -> str:
    """
    Conditional edge function: determine if we should retry or proceed.

    Returns:
        - "health_advisor" / "medication_agent" / "insight_analyst" / "direct_answer": Retry the specific agent
        - "done": Proceed to synthesize
    """
    reflection_passed = state.get("reflection_passed", True)
    retry_count = state.get("reflection_retry_count", 0)
    agent_used = state.get("agent_used", "direct_answer")

    if not reflection_passed and retry_count < 2:
        # Return the specific agent to retry
        valid_agents = {"health_advisor", "medication_agent", "insight_analyst", "direct_answer"}
        if agent_used in valid_agents:
            return agent_used
        return "direct_answer"  # Fallback

    return "done"
