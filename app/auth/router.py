"""
Auth API router — register, login, refresh, me.
"""

from __future__ import annotations

import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.auth.service import (
    create_access_token,
    create_refresh_token,
    create_user,
    decode_token,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    verify_password,
)
from app.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Dependency: current user ─────────────────────────────


from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    """Extract and validate JWT from Authorization header."""
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = uuid.UUID(payload["sub"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


# ── Endpoints ────────────────────────────────────────────


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if await get_user_by_username(db, req.username):
        raise HTTPException(status_code=409, detail="Username already exists")
    if await get_user_by_email(db, req.email):
        raise HTTPException(status_code=409, detail="Email already registered")

    user = await create_user(db, req.username, req.email, req.password, req.display_name)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_username(db, req.username)
    if user is None or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    access_token, expires_in = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(req.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = uuid.UUID(payload["sub"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = await get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    access_token, expires_in = create_access_token(user.id)
    new_refresh = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=expires_in,
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user=Depends(get_current_user)):
    return current_user
