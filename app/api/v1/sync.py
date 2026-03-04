"""
Data Sync API — handles health data synchronization from Android app.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.router import get_current_user
from app.database import get_db
from app.models.health_data import (
    DailyAdvice,
    DailySummary,
    HealthEntry,
    QuestionResponse,
)
from app.models.medication import Medication, MedicationCourse
from app.models.user import User
from app.schemas.health import (
    SyncResponse,
    SyncStatusResponse,
    SyncUploadRequest,
)

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/upload", response_model=SyncResponse)
async def sync_upload(
    req: SyncUploadRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Receive incremental data from Android app.
    Conflict resolution: client-first (Android is the data authority).
    """
    entries_synced = 0
    meds_synced = 0

    # Sync health entries
    for entry_data in req.entries:
        # Check if entry already exists for this date
        stmt = select(HealthEntry).where(
            HealthEntry.user_id == current_user.id,
            HealthEntry.entry_date == entry_data.entry_date,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Client-first: update existing
            existing.timezone_id = entry_data.timezone_id
            existing.android_id = entry_data.android_id
            existing.synced_at = datetime.now(timezone.utc)

            # Delete and re-create question responses
            from sqlalchemy import delete
            await db.execute(
                delete(QuestionResponse).where(QuestionResponse.entry_id == existing.id)
            )
            entry_id = existing.id
        else:
            # Create new entry
            entry = HealthEntry(
                user_id=current_user.id,
                entry_date=entry_data.entry_date,
                timezone_id=entry_data.timezone_id,
                android_id=entry_data.android_id,
                created_at=datetime.fromtimestamp(
                    entry_data.created_at / 1000, tz=timezone.utc
                ),
            )
            db.add(entry)
            await db.flush()
            entry_id = entry.id

        # Add question responses
        for qr in entry_data.question_responses:
            db.add(QuestionResponse(
                entry_id=entry_id,
                question_id=qr.question_id,
                step_index=qr.step_index,
                answer_type=qr.answer_type,
                answer_value=qr.answer_value,
                answer_label=qr.answer_label,
                metadata_json=qr.metadata_json,
            ))

        # Sync daily advice if present
        if entry_data.daily_advice:
            from sqlalchemy import delete
            await db.execute(
                delete(DailyAdvice).where(DailyAdvice.entry_id == entry_id)
            )
            db.add(DailyAdvice(
                entry_id=entry_id,
                model=entry_data.daily_advice.model,
                advice_json=entry_data.daily_advice.advice_json,
                prompt_hash=entry_data.daily_advice.prompt_hash,
            ))

        # Sync daily summary if present
        if entry_data.daily_summary:
            from sqlalchemy import delete
            await db.execute(
                delete(DailySummary).where(DailySummary.entry_id == entry_id)
            )
            db.add(DailySummary(
                entry_id=entry_id,
                window_7d_json=entry_data.daily_summary.window_7d_json,
                window_30d_json=entry_data.daily_summary.window_30d_json,
            ))

        entries_synced += 1

    # Sync medications
    for med_data in req.medications:
        stmt = select(Medication).where(
            Medication.user_id == current_user.id,
            Medication.android_id == med_data.android_id,
        )
        result = await db.execute(stmt)
        existing_med = result.scalar_one_or_none()

        if existing_med:
            existing_med.name = med_data.name
            existing_med.aliases = med_data.aliases
            existing_med.note = med_data.note
            existing_med.info_summary = med_data.info_summary
        else:
            db.add(Medication(
                user_id=current_user.id,
                android_id=med_data.android_id,
                name=med_data.name,
                aliases=med_data.aliases,
                note=med_data.note,
                info_summary=med_data.info_summary,
            ))
        meds_synced += 1

    # Sync medication courses
    for course_data in req.medication_courses:
        # Find medication by android_id
        stmt = select(Medication).where(
            Medication.user_id == current_user.id,
            Medication.android_id == course_data.med_android_id,
        )
        result = await db.execute(stmt)
        med = result.scalar_one_or_none()
        if med:
            db.add(MedicationCourse(
                med_id=med.id,
                start_date=course_data.start_date,
                end_date=course_data.end_date,
                status=course_data.status,
                frequency_text=course_data.frequency_text,
                dose_text=course_data.dose_text,
                time_hints=course_data.time_hints,
            ))

    await db.flush()

    return SyncResponse(
        message="Sync completed",
        entries_synced=entries_synced,
        medications_synced=meds_synced,
        server_timestamp=int(time.time() * 1000),
    )


@router.get("/status", response_model=SyncStatusResponse)
async def sync_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return server data status for sync coordination."""
    entries_count = await db.execute(
        select(func.count(HealthEntry.id)).where(
            HealthEntry.user_id == current_user.id
        )
    )
    meds_count = await db.execute(
        select(func.count(Medication.id)).where(
            Medication.user_id == current_user.id
        )
    )

    # Get latest entry timestamp
    latest = await db.execute(
        select(func.max(HealthEntry.synced_at)).where(
            HealthEntry.user_id == current_user.id
        )
    )
    latest_ts = latest.scalar_one_or_none()
    ts = int(latest_ts.timestamp() * 1000) if latest_ts else 0

    return SyncStatusResponse(
        last_sync_timestamp=ts,
        total_entries=entries_count.scalar_one() or 0,
        total_medications=meds_count.scalar_one() or 0,
    )
