"""
Auth API router — register, login, refresh, me.
"""

from __future__ import annotations

import asyncio
import uuid

import asyncpg
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import IntegrityError
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


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    for attempt in range(4):
        try:
            if await get_user_by_username(db, req.username):
                raise HTTPException(status_code=409, detail="Username already exists")
            if await get_user_by_email(db, req.email):
                raise HTTPException(status_code=409, detail="Email already registered")

            try:
                user = await create_user(db, req.username, req.email, req.password, req.display_name)
            except IntegrityError as exc:
                detail = str(getattr(exc, "orig", exc)).lower()
                if "username" in detail:
                    raise HTTPException(status_code=409, detail="Username already exists")
                if "email" in detail:
                    raise HTTPException(status_code=409, detail="Email already registered")
                raise HTTPException(status_code=409, detail="User already exists")

            access_token, expires_in = create_access_token(user.id)
            refresh_token = create_refresh_token(user.id)
            return TokenResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=expires_in,
            )
        except Exception as exc:
            if not _is_transient_db_error(exc) or attempt == 3:
                raise
            await db.rollback()
            await asyncio.sleep(0.25 * (attempt + 1))


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    for attempt in range(4):
        try:
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
        except Exception as exc:
            if not _is_transient_db_error(exc) or attempt == 3:
                raise
            await db.rollback()
            await asyncio.sleep(0.25 * (attempt + 1))


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


def _is_transient_db_error(exc: Exception) -> bool:
    if isinstance(exc, HTTPException):
        return False
    if isinstance(exc, asyncpg.PostgresConnectionError):
        return True
    if isinstance(exc, DBAPIError) and isinstance(getattr(exc, "orig", None), asyncpg.PostgresConnectionError):
        return True
    text = str(exc).lower()
    markers = (
        "connection was closed in the middle of operation",
        "connection_lost",
        "targetserverattributenotmatched",
        "connection refused",
    )
    return any(marker in text for marker in markers)
