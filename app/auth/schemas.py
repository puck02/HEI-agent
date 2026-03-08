"""
Auth Pydantic schemas for request / response validation.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ── Request ──────────────────────────────────────────────


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    display_name: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Response ─────────────────────────────────────────────


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    display_name: str | None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
