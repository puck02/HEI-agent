"""Completion schemas — unified LLM completion request/response."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CompletionRequest(BaseModel):
    """Unified LLM completion request.

    Frontend sends this to /completion instead of directly calling LLM.
    """

    message: str = Field(..., min_length=1, max_length=4096)
    session_id: str | None = None
    mode: Literal["fast", "agent", "auto"] = Field(
        default="auto",
        description=(
            "Pipeline mode: "
            "'fast' = single LLM call (3-15s), "
            "'agent' = full LangGraph with reflection (10-30s), "
            "'auto' = system decides based on message complexity"
        ),
    )


class CompletionResponse(BaseModel):
    """Unified LLM completion response."""

    answer: str
    session_id: str
    mode_used: str = Field(description="Actual mode used: 'fast' or 'agent'")
    agent_used: str | None = None
    model_used: str | None = None
    response_time_ms: int | None = None
    reflection_scores: dict[str, Any] = Field(default_factory=dict)
    trace: list[dict[str, Any]] = Field(default_factory=list)
