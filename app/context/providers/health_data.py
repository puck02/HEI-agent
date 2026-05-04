"""Health data context provider — fetches recent health diary entries."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.health_data import HealthEntry

log = structlog.get_logger(__name__)


async def fetch_health_context(db: AsyncSession, user_id: uuid.UUID, days: int = 7) -> str:
    """Query recent health entries and format as context string."""
    since = date.today() - timedelta(days=days)
    stmt = (
        select(HealthEntry)
        .where(HealthEntry.user_id == user_id, HealthEntry.entry_date >= since)
        .options(selectinload(HealthEntry.question_responses))
        .order_by(HealthEntry.entry_date.desc())
    )
    result = await db.execute(stmt)
    entries = result.scalars().all()
    if not entries:
        return ""

    lines = []
    for entry in entries:
        day = entry.entry_date.isoformat()
        answers = "; ".join(
            f"{r.question_id}={r.answer_label or r.answer_value}"
            for r in entry.question_responses
        )
        lines.append(f"{day}: {answers}")
    return "用户最近7天健康日报:\n" + "\n".join(lines)
