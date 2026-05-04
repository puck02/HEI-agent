"""ReflectionScorer — evaluates responses using a pluggable ReflectionPolicy."""

from __future__ import annotations

import structlog

from app.llm.router import get_llm_router
from app.reflection.base import ReflectionPolicy
from app.reflection.policies.general_policy import GeneralPolicy
from app.reflection.policies.health_policy import HealthPolicy
from app.utils.json_parser import parse_llm_json

log = structlog.get_logger(__name__)

# Map agent names to their default policies
_DEFAULT_POLICY_MAP: dict[str, type[ReflectionPolicy]] = {
    "health_advisor": HealthPolicy,
    "medication_agent": HealthPolicy,
    "insight_analyst": HealthPolicy,
    "direct_answer": GeneralPolicy,
    "general": GeneralPolicy,
}


def get_policy_for_agent(agent_used: str) -> ReflectionPolicy:
    """Get the default reflection policy for a given agent."""
    policy_cls = _DEFAULT_POLICY_MAP.get(agent_used, GeneralPolicy)
    return policy_cls()


class ReflectionScorer:
    """Evaluates agent responses using a pluggable ReflectionPolicy.

    Generates prompts dynamically from the policy's dimensions,
    calls the LLM for scoring, and applies the policy's pass/fail criteria.
    """

    def __init__(self, policy: ReflectionPolicy | None = None) -> None:
        self._policy = policy

    async def evaluate(
        self,
        user_message: str,
        response: str,
        agent_used: str,
        policy: ReflectionPolicy | None = None,
    ) -> dict:
        """Evaluate a response using the given or default policy.

        Args:
            user_message: The original user message.
            response: The agent's generated response.
            agent_used: Name of the agent that generated the response.
            policy: Override policy (if None, uses default for the agent).

        Returns:
            Dict with keys: scores, total_score, issues, should_retry,
            improved_response, policy_name, passed.
        """
        active_policy = policy or self._policy or get_policy_for_agent(agent_used)
        router = get_llm_router()

        # Build prompt dynamically from policy dimensions
        scoring_prompt = active_policy.build_prompt()

        prompt = (
            "你是一个严格的回答质量审核员。请评估以下 AI 助手的回答质量。\n\n"
            f"【用户问题】\n{user_message}\n\n"
            f"【使用的 Agent】\n{agent_used}\n\n"
            f"【AI 回答】\n{response}\n\n"
            f"{scoring_prompt}\n\n"
            "评判标准：\n"
            f"- 总分 >= {int(active_policy.max_total_score * 0.8)}: 通过，should_retry = false\n"
            f"- 总分 < {int(active_policy.max_total_score * 0.8)}: 需要改进，should_retry = true\n"
            "- 如果安全边界（safety）得分为 0: 必须重试"
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
            total_score = reflection.get("total_score", 0)
            issues = reflection.get("issues", [])
            should_retry = reflection.get("should_retry", False)
            improved_response = reflection.get("improved_response")

            # Apply policy's passing criteria
            scores_with_total = {**scores, "total": total_score}
            passed = active_policy.passing_criteria(scores_with_total)

            # Safety violation always forces retry
            if scores.get("safety", 2) == 0:
                should_retry = True
                passed = False
                log.warning("reflection_safety_violation", issues=issues)

            log.info(
                "reflection_result",
                policy=active_policy.__class__.__name__,
                total_score=total_score,
                scores=scores,
                issues=issues,
                should_retry=should_retry,
                passed=passed,
            )

            return {
                "scores": scores,
                "total_score": total_score,
                "issues": issues,
                "should_retry": should_retry,
                "improved_response": improved_response,
                "policy_name": active_policy.__class__.__name__,
                "passed": passed,
            }

        except Exception as e:
            log.error("reflection_scorer_error", error=str(e))
            # Fail-open: pass through on error
            return {
                "scores": {},
                "total_score": 10,
                "issues": [],
                "should_retry": False,
                "improved_response": None,
                "policy_name": active_policy.__class__.__name__,
                "passed": True,
            }
