"""
Session Pydantic schemas — request / response models for session management.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str | None = None


class SessionUpdate(BaseModel):
    title: str | None = None


class MessageOut(BaseModel):
    role: str
    content: str
    timestamp: str


class SessionOut(BaseModel):
    session_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0


class SessionDetailOut(BaseModel):
    session_id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[MessageOut] = Field(default_factory=list)


class SessionListOut(BaseModel):
    sessions: list[SessionOut]
