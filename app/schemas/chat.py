"""
Chat Pydantic schemas — Agent conversation request / response.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4096)
    session_id: str | None = None
    context_type: str | None = None  # daily_report / medication / general


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    agent_used: str | None = None
    model_used: str | None = None


class StreamEvent(BaseModel):
    """SSE event payload."""
    event: str  # token / done / error
    data: str
