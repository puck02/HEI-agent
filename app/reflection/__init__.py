"""Reflection module — pluggable response quality evaluation."""

from app.reflection.base import ReflectionPolicy, ScoringDimension
from app.reflection.scorer import ReflectionScorer, get_policy_for_agent
from app.reflection.policies.health_policy import HealthPolicy
from app.reflection.policies.general_policy import GeneralPolicy

__all__ = [
    "ReflectionPolicy",
    "ScoringDimension",
    "ReflectionScorer",
    "get_policy_for_agent",
    "HealthPolicy",
    "GeneralPolicy",
]
