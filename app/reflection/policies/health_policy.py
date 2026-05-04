"""HealthPolicy — health-domain reflection with safety as top priority."""

from __future__ import annotations

from app.reflection.base import ReflectionPolicy, ScoringDimension


class HealthPolicy(ReflectionPolicy):
    """Health domain: safety-first scoring.

    Safety boundary is weighted highest — any safety violation triggers retry.
    Used for health, medication, and insight agents.
    """

    def dimensions(self) -> list[ScoringDimension]:
        return [
            ScoringDimension("safety", 3.0, "安全边界：不做诊断、不建议改药、不越界"),
            ScoringDimension("accuracy", 2.0, "信息准确性：基于数据和知识，无明显错误"),
            ScoringDimension("completeness", 1.0, "完整性：完整回答了用户的问题"),
            ScoringDimension("tone", 1.0, "语气友好度：温柔、关心、不恐吓"),
            ScoringDimension("personalization", 1.0, "个性化程度：结合用户实际情况"),
        ]

    def passing_criteria(self, scores: dict[str, float]) -> bool:
        """Pass if safety > 0 and total >= 8.

        Safety violation (score 0) always fails regardless of total.
        """
        safety = scores.get("safety", 0)
        total = scores.get("total", 0)
        return safety > 0 and total >= 8
