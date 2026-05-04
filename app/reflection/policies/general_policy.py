"""GeneralPolicy — general conversation reflection with accuracy as top priority."""

from __future__ import annotations

from app.reflection.base import ReflectionPolicy, ScoringDimension


class GeneralPolicy(ReflectionPolicy):
    """General conversation: accuracy-first scoring.

    Lighter evaluation — no safety boundary check needed for casual chat.
    Used for the general/direct_answer agent.
    """

    def dimensions(self) -> list[ScoringDimension]:
        return [
            ScoringDimension("accuracy", 3.0, "信息准确性：回答内容正确无误"),
            ScoringDimension("completeness", 2.0, "完整性：回答了用户的问题"),
            ScoringDimension("tone", 1.0, "语气友好度：自然、友好、符合人设"),
        ]

    def passing_criteria(self, scores: dict[str, float]) -> bool:
        """Pass if total >= 6."""
        return scores.get("total", 0) >= 6
