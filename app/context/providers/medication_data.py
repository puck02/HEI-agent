"""Medication data context provider — fetches active medications."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.medication import Medication

log = structlog.get_logger(__name__)


async def fetch_medication_context(db: AsyncSession, user_id: uuid.UUID) -> str:
    """Query active medications and format as context string."""
    stmt = (
        select(Medication)
        .where(Medication.user_id == user_id)
        .options(selectinload(Medication.courses))
    )
    result = await db.execute(stmt)
    meds = result.scalars().all()
    if not meds:
        return ""

    lines = []
    for med in meds:
        courses_str = ""
        if med.courses:
            active = [c for c in med.courses if c.status == "active"]
            if active:
                c = active[0]
                courses_str = f" (剂量:{c.dose_text or '未知'}, 频次:{c.frequency_text or '未知'})"
        lines.append(f"- {med.name}{courses_str}")
    return "用户当前用药:\n" + "\n".join(lines)
