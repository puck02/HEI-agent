"""
JWT token creation, password hashing, and authentication service.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Password helpers ─────────────────────────────────────


def hash_password(password: str) -> str:
    # bcrypt has a 72-byte limit, truncate if necessary
    password_bytes = password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    return pwd_context.hash(password_bytes)


def verify_password(plain: str, hashed: str) -> bool:
    # bcrypt has a 72-byte limit, truncate if necessary
    plain_bytes = plain.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    return pwd_context.verify(plain_bytes, hashed)


# ── JWT helpers ──────────────────────────────────────────


def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    """Return (token, expires_in_seconds)."""
    expires_delta = timedelta(minutes=settings.jwt_access_token_expire_minutes)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": str(user_id),
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, int(expires_delta.total_seconds())


def create_refresh_token(user_id: uuid.UUID) -> str:
    expires_delta = timedelta(days=settings.jwt_refresh_token_expire_days)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises jwt.PyJWTError on failure."""
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )


# ── Database operations ──────────────────────────────────


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    return await _scalar_one_or_none_with_retry(
        db,
        select(User).where(User.username == username),
    )


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    return await _scalar_one_or_none_with_retry(
        db,
        select(User).where(User.email == email),
    )


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await _scalar_one_or_none_with_retry(
        db,
        select(User).where(User.id == user_id),
    )


async def create_user(
    db: AsyncSession,
    username: str,
    email: str,
    password: str,
    display_name: str | None = None,
) -> User:
    for attempt in range(3):
        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            display_name=display_name,
        )
        db.add(user)
        try:
            await db.flush()
            await db.refresh(user)
            await db.commit()
            return user
        except Exception as exc:
            if not _is_transient_db_connection_error(exc) or attempt == 2:
                raise
            await db.rollback()
            await asyncio.sleep(0.2 * (attempt + 1))


async def _scalar_one_or_none_with_retry(db: AsyncSession, stmt):
    for attempt in range(3):
        try:
            result = await db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as exc:
            if not _is_transient_db_connection_error(exc) or attempt == 2:
                raise
            await db.rollback()
            await asyncio.sleep(0.2 * (attempt + 1))


def _is_transient_db_connection_error(exc: Exception) -> bool:
    if isinstance(exc, asyncpg.PostgresConnectionError):
        return True
    if isinstance(exc, DBAPIError) and isinstance(getattr(exc, "orig", None), asyncpg.PostgresConnectionError):
        return True

    text = str(exc).lower()
    transient_markers = (
        "connection was closed in the middle of operation",
        "connection_lost",
        "targetserverattributenotmatched",
        "connection refused",
    )
    return any(marker in text for marker in transient_markers)
