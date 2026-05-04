"""Reflection policy abstractions — pluggable scoring dimensions and criteria."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ScoringDimension:
    """A single evaluation dimension with weight and description."""

    name: str
    weight: float
    description: str

    def prompt_line(self, max_score: int = 2) -> str:
        """Generate a prompt line for this dimension."""
        return f"- **{self.name}** (权重 {self.weight}): {self.description} (0-{max_score}分)"


class ReflectionPolicy(ABC):
    """Abstract base class for reflection scoring policies.

    Subclasses define domain-specific dimensions and pass/fail criteria.
    """

    @abstractmethod
    def dimensions(self) -> list[ScoringDimension]:
        """Return the scoring dimensions for this policy."""

    @abstractmethod
    def passing_criteria(self, scores: dict[str, float]) -> bool:
        """Determine if the response passes quality checks.

        Args:
            scores: Dict mapping dimension names to scores, with 'total' as the sum.

        Returns:
            True if the response is acceptable.
        """

    @property
    def max_total_score(self) -> float:
        """Maximum possible total score (sum of weights * max per-dimension score)."""
        return sum(d.weight * 2 for d in self.dimensions())

    @property
    def dimension_names(self) -> list[str]:
        """List of dimension names."""
        return [d.name for d in self.dimensions()]

    def build_prompt(self) -> str:
        """Dynamically generate a scoring prompt based on dimensions."""
        dim_lines = "\n".join(
            f"{i+1}. {d.prompt_line()}" for i, d in enumerate(self.dimensions())
        )
        names_json = ", ".join(f'"{d.name}": 0-2' for d in self.dimensions())

        return (
            f"请从以下 {len(self.dimensions())} 个维度评估回答质量：\n\n"
            f"{dim_lines}\n\n"
            f"请返回 JSON 格式：\n"
            f'{{{{\n'
            f'    "scores": {{{names_json}}},\n'
            f'    "total_score": <总分>,\n'
            f'    "issues": ["问题1", "问题2"],\n'
            f'    "should_retry": true/false,\n'
            f'    "improved_response": "如果 should_retry=true，提供改进后的完整回答；否则为 null"\n'
            f'}}}}'
        )
