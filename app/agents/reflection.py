"""
Reflection Node — Self-evaluation and quality assurance for agent responses.

Uses the pluggable ReflectionScorer with domain-specific policies:
- HealthPolicy: safety-first for health/medication/insight agents
- GeneralPolicy: accuracy-first for general conversation

If the response fails quality checks, it generates an improved version.
Maximum 2 retries to prevent infinite loops.
"""

from __future__ import annotations

import structlog

from app.agents.state import AgentState
from app.reflection.scorer import ReflectionScorer

log = structlog.get_logger(__name__)

# ── Module-level scorer instance ──────────────────────────────────────────────

_scorer = ReflectionScorer()


# ── Reflection Node ──────────────────────────────────────────────────────────


async def reflection_node(state: AgentState) -> dict:
    """
    Reflection node: evaluate response quality and retry if needed.

    Uses ReflectionScorer with domain-specific policies:
    - Health/medication/insight agents → HealthPolicy (safety-first)
    - General agent → GeneralPolicy (accuracy-first)

    Max 2 retries to prevent infinite loops.
    """
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

    result = await _scorer.evaluate(
        user_message=user_message,
        response=response,
        agent_used=agent_used,
    )

    scores = result["scores"]
    should_retry = result["should_retry"]
    improved_response = result["improved_response"]

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
