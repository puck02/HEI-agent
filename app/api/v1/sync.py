"""
Data Sync API — handles health data synchronization from Android app.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.router import get_current_user
from app.database import get_db
from app.models.health_data import (
    AdviceTracking,
    DailyAdvice,
    DailySummary,
    HealthEntry,
    InsightReport,
    QuestionResponse,
    SyncTombstoneRecord,
)
from app.models.medication import Medication, MedicationCourse, MedicationEvent
from app.models.memory import MemoryEntry
from app.models.user import User
from app.memory.manager import get_memory_manager
from app.schemas.health import (
    SyncChange,
    SyncEntityEnvelope,
    SyncPullResponse,
    SyncPushRequest,
    SyncPushResponse,
    SyncPushResult,
    SyncResponse,
    SyncStatusResponse,
    SyncTombstone,
    SyncUploadRequest,
)

router = APIRouter(prefix="/sync", tags=["sync"])


async def _record_tombstone(
    db: AsyncSession,
    user_id,
    entity: str,
    record_id: int,
    payload: dict | None = None,
) -> None:
    db.add(SyncTombstoneRecord(
        user_id=user_id,
        entity=entity,
        record_id=record_id,
        payload_json=payload,
        deleted_at=datetime.now(timezone.utc),
    ))


async def _compute_server_cursor(db: AsyncSession, user_id) -> int:
    entry_latest = (await db.execute(
        select(func.max(HealthEntry.synced_at)).where(HealthEntry.user_id == user_id)
    )).scalar_one_or_none()

    med_latest = (await db.execute(
        select(func.max(Medication.updated_at)).where(Medication.user_id == user_id)
    )).scalar_one_or_none()

    course_latest = (await db.execute(
        select(func.max(MedicationCourse.updated_at))
        .join(Medication, MedicationCourse.med_id == Medication.id)
        .where(Medication.user_id == user_id)
    )).scalar_one_or_none()

    tomb_latest = (await db.execute(
        select(func.max(SyncTombstoneRecord.deleted_at)).where(SyncTombstoneRecord.user_id == user_id)
    )).scalar_one_or_none()

    return max(
        _to_millis(entry_latest),
        _to_millis(med_latest),
        _to_millis(course_latest),
        _to_millis(tomb_latest),
    )


def _to_millis(value: datetime | None) -> int:
    if value is None:
        return 0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


def _now_millis() -> int:
    return int(time.time() * 1000)


def _parse_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    return None


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
        server_timestamp=_now_millis(),
    )


async def _apply_change(db: AsyncSession, user: User, change: SyncChange) -> SyncPushResult:
    entity = change.entity
    op = change.op
    payload = change.payload
    now = datetime.now(timezone.utc)

    try:
        if entity == "health_entry":
            android_id = payload.get("android_id")
            if android_id is None:
                return SyncPushResult(entity=entity, op=op, status="failed", conflict_reason="missing android_id")

            stmt = select(HealthEntry).where(
                HealthEntry.user_id == user.id,
                HealthEntry.android_id == android_id,
            )
            existing = (await db.execute(stmt)).scalar_one_or_none()

            if op == "delete":
                if existing:
                    await _record_tombstone(
                        db,
                        user.id,
                        "health_entry",
                        int(existing.android_id or existing.id),
                        payload={
                            "android_id": existing.android_id,
                            "entry_date": existing.entry_date.isoformat(),
                        },
                    )
                    await db.delete(existing)
                    return SyncPushResult(entity=entity, op=op, status="applied", android_id=android_id)
                return SyncPushResult(entity=entity, op=op, status="ignored", android_id=android_id)

            entry_date = _parse_date(payload.get("entry_date"))
            if entry_date is None:
                return SyncPushResult(entity=entity, op=op, status="failed", conflict_reason="missing entry_date")

            if existing:
                existing.entry_date = entry_date
                existing.timezone_id = payload.get("timezone_id")
                existing.synced_at = now
                await db.execute(delete(QuestionResponse).where(QuestionResponse.entry_id == existing.id))
                entry = existing
            else:
                entry = HealthEntry(
                    user_id=user.id,
                    android_id=android_id,
                    entry_date=entry_date,
                    timezone_id=payload.get("timezone_id"),
                    created_at=now,
                    synced_at=now,
                )
                db.add(entry)
                await db.flush()

            for item in payload.get("question_responses", []):
                db.add(QuestionResponse(
                    entry_id=entry.id,
                    question_id=item.get("question_id", ""),
                    step_index=item.get("step_index", 0),
                    answer_type=item.get("answer_type", "choice"),
                    answer_value=item.get("answer_value"),
                    answer_label=item.get("answer_label"),
                    metadata_json=item.get("metadata_json"),
                ))

            return SyncPushResult(
                entity=entity,
                op=op,
                status="applied",
                android_id=android_id,
                server_id=entry.id,
                server_version=_to_millis(entry.synced_at),
            )

        if entity == "medication":
            android_id = payload.get("android_id")
            if android_id is None:
                return SyncPushResult(entity=entity, op=op, status="failed", conflict_reason="missing android_id")

            stmt = select(Medication).where(
                Medication.user_id == user.id,
                Medication.android_id == android_id,
            )
            existing = (await db.execute(stmt)).scalar_one_or_none()

            if op == "delete":
                if existing:
                    await _record_tombstone(
                        db,
                        user.id,
                        "medication",
                        int(existing.android_id or existing.id),
                        payload={
                            "android_id": existing.android_id,
                            "name": existing.name,
                        },
                    )
                    await db.delete(existing)
                    return SyncPushResult(entity=entity, op=op, status="applied", android_id=android_id)
                return SyncPushResult(entity=entity, op=op, status="ignored", android_id=android_id)

            if existing:
                existing.name = payload.get("name", existing.name)
                existing.aliases = payload.get("aliases")
                existing.note = payload.get("note")
                existing.info_summary = payload.get("info_summary")
                existing.updated_at = now
                medication = existing
            else:
                medication = Medication(
                    user_id=user.id,
                    android_id=android_id,
                    name=payload.get("name", "未命名药品"),
                    aliases=payload.get("aliases"),
                    note=payload.get("note"),
                    info_summary=payload.get("info_summary"),
                    created_at=now,
                    updated_at=now,
                )
                db.add(medication)
                await db.flush()

            return SyncPushResult(
                entity=entity,
                op=op,
                status="applied",
                android_id=android_id,
                server_id=medication.id,
                server_version=_to_millis(medication.updated_at),
            )

        if entity == "medication_course":
            med_android_id = payload.get("med_android_id")
            if med_android_id is None:
                return SyncPushResult(entity=entity, op=op, status="failed", conflict_reason="missing med_android_id")

            med_stmt = select(Medication).where(
                Medication.user_id == user.id,
                Medication.android_id == med_android_id,
            )
            medication = (await db.execute(med_stmt)).scalar_one_or_none()
            if medication is None:
                return SyncPushResult(entity=entity, op=op, status="conflict", conflict_reason="medication not found")

            if op == "delete":
                course_id = payload.get("record_id")
                start_date = _parse_date(payload.get("start_date"))
                status = payload.get("status")

                course_stmt = select(MedicationCourse).where(MedicationCourse.med_id == medication.id)
                if course_id is not None:
                    course_stmt = course_stmt.where(MedicationCourse.id == course_id)
                if start_date is not None:
                    course_stmt = course_stmt.where(MedicationCourse.start_date == start_date)
                if status is not None:
                    course_stmt = course_stmt.where(MedicationCourse.status == status)

                course = (await db.execute(course_stmt.order_by(MedicationCourse.updated_at.desc()))).scalar_one_or_none()
                if course is None:
                    return SyncPushResult(entity=entity, op=op, status="ignored", conflict_reason="course not found")

                await _record_tombstone(
                    db,
                    user.id,
                    "medication_course",
                    int(course.id),
                    payload={
                        "med_android_id": med_android_id,
                        "start_date": course.start_date.isoformat(),
                        "status": course.status,
                    },
                )
                await db.delete(course)
                return SyncPushResult(entity=entity, op=op, status="applied", server_id=course.id)

            start_date = _parse_date(payload.get("start_date"))
            if start_date is None:
                return SyncPushResult(entity=entity, op=op, status="failed", conflict_reason="missing start_date")

            end_date = _parse_date(payload.get("end_date"))

            course = MedicationCourse(
                med_id=medication.id,
                start_date=start_date,
                end_date=end_date,
                status=payload.get("status", "active"),
                frequency_text=payload.get("frequency_text"),
                dose_text=payload.get("dose_text"),
                time_hints=payload.get("time_hints"),
                created_at=now,
                updated_at=now,
            )
            db.add(course)
            await db.flush()
            return SyncPushResult(
                entity=entity,
                op=op,
                status="applied",
                server_id=course.id,
                server_version=_to_millis(course.updated_at),
            )

        return SyncPushResult(entity=entity, op=op, status="ignored", conflict_reason="unsupported entity")
    except Exception as exc:
        return SyncPushResult(entity=entity, op=op, status="failed", conflict_reason=str(exc))


@router.post("/push", response_model=SyncPushResponse)
async def sync_push(
    req: SyncPushRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_cursor = await _compute_server_cursor(db, current_user.id)
    if req.base_server_version > 0 and req.base_server_version < current_cursor:
        conflict_results = [
            SyncPushResult(
                entity=change.entity,
                op=change.op,
                status="conflict",
                conflict_reason="server has newer data; pull and retry",
            )
            for change in req.changes
        ]
        return SyncPushResponse(
            message="Sync push rejected due to stale base_server_version",
            accepted=len(req.changes),
            applied=0,
            conflicts=len(conflict_results),
            server_timestamp=current_cursor,
            server_cursor=current_cursor,
            results=conflict_results,
        )

    results: list[SyncPushResult] = []
    applied = 0
    conflicts = 0

    for change in req.changes:
        result = await _apply_change(db, current_user, change)
        results.append(result)
        if result.status == "applied":
            applied += 1
        if result.status == "conflict":
            conflicts += 1

    await db.flush()
    cursor = _now_millis()

    return SyncPushResponse(
        message="Sync push completed",
        accepted=len(req.changes),
        applied=applied,
        conflicts=conflicts,
        server_timestamp=cursor,
        server_cursor=cursor,
        results=results,
    )


@router.get("/pull", response_model=SyncPullResponse)
async def sync_pull(
    since: int = 0,
    limit: int = 200,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if limit <= 0 or limit > 1000:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 1000")

    since_dt = datetime.fromtimestamp(since / 1000, tz=timezone.utc) if since > 0 else datetime.fromtimestamp(0, tz=timezone.utc)
    changes: list[SyncEntityEnvelope] = []

    entry_stmt = (
        select(HealthEntry)
        .where(HealthEntry.user_id == current_user.id, HealthEntry.synced_at >= since_dt)
        .order_by(HealthEntry.synced_at.asc())
        .limit(limit)
    )
    entries = (await db.execute(entry_stmt)).scalars().all()
    for entry in entries:
        response_stmt = select(QuestionResponse).where(QuestionResponse.entry_id == entry.id)
        responses = (await db.execute(response_stmt)).scalars().all()

        advice_stmt = select(DailyAdvice).where(DailyAdvice.entry_id == entry.id)
        advice = (await db.execute(advice_stmt)).scalar_one_or_none()

        summary_stmt = select(DailySummary).where(DailySummary.entry_id == entry.id)
        summary = (await db.execute(summary_stmt)).scalar_one_or_none()

        payload = {
            "android_id": entry.android_id,
            "entry_date": entry.entry_date,
            "timezone_id": entry.timezone_id,
            "created_at": _to_millis(entry.created_at),
            "question_responses": [
                {
                    "question_id": item.question_id,
                    "step_index": item.step_index,
                    "answer_type": item.answer_type,
                    "answer_value": item.answer_value,
                    "answer_label": item.answer_label,
                    "metadata_json": item.metadata_json,
                }
                for item in responses
            ],
        }

        if advice:
            payload["daily_advice"] = {
                "model": advice.model,
                "advice_json": advice.advice_json,
                "prompt_hash": advice.prompt_hash,
                "generated_at": _to_millis(advice.generated_at),
            }

        if summary:
            payload["daily_summary"] = {
                "window_7d_json": summary.window_7d_json,
                "window_30d_json": summary.window_30d_json,
                "computed_at": _to_millis(summary.computed_at),
            }

        changes.append(
            SyncEntityEnvelope(
                entity="health_entry",
                record_id=entry.id,
                server_version=_to_millis(entry.synced_at),
                updated_at=_to_millis(entry.synced_at),
                payload=payload,
            )
        )

    med_stmt = (
        select(Medication)
        .where(Medication.user_id == current_user.id, Medication.updated_at >= since_dt)
        .order_by(Medication.updated_at.asc())
        .limit(limit)
    )
    meds = (await db.execute(med_stmt)).scalars().all()
    for med in meds:
        changes.append(
            SyncEntityEnvelope(
                entity="medication",
                record_id=med.id,
                server_version=_to_millis(med.updated_at),
                updated_at=_to_millis(med.updated_at),
                payload={
                    "android_id": med.android_id,
                    "name": med.name,
                    "aliases": med.aliases,
                    "note": med.note,
                    "info_summary": med.info_summary,
                },
            )
        )

    course_stmt = (
        select(MedicationCourse, Medication)
        .join(Medication, MedicationCourse.med_id == Medication.id)
        .where(Medication.user_id == current_user.id, MedicationCourse.updated_at >= since_dt)
        .order_by(MedicationCourse.updated_at.asc())
        .limit(limit)
    )
    course_rows = (await db.execute(course_stmt)).all()
    for course, med in course_rows:
        changes.append(
            SyncEntityEnvelope(
                entity="medication_course",
                record_id=course.id,
                server_version=_to_millis(course.updated_at),
                updated_at=_to_millis(course.updated_at),
                payload={
                    "med_android_id": med.android_id,
                    "start_date": course.start_date,
                    "end_date": course.end_date,
                    "status": course.status,
                    "frequency_text": course.frequency_text,
                    "dose_text": course.dose_text,
                    "time_hints": course.time_hints,
                },
            )
        )

    changes.sort(key=lambda item: item.server_version)
    if len(changes) > limit:
        changes = changes[:limit]

    tomb_stmt = (
        select(SyncTombstoneRecord)
        .where(SyncTombstoneRecord.user_id == current_user.id, SyncTombstoneRecord.deleted_at >= since_dt)
        .order_by(SyncTombstoneRecord.deleted_at.asc())
        .limit(limit)
    )
    tomb_rows = (await db.execute(tomb_stmt)).scalars().all()
    tombstones = [
        SyncTombstone(
            entity=row.entity,
            record_id=row.record_id,
            deleted_at=_to_millis(row.deleted_at),
            payload=row.payload_json or {},
        )
        for row in tomb_rows
    ]

    all_versions = [item.server_version for item in changes] + [item.deleted_at for item in tombstones]
    next_cursor = max(all_versions) if all_versions else since
    now_ms = _now_millis()

    return SyncPullResponse(
        changes=changes,
        tombstones=tombstones,
        next_cursor=next_cursor,
        server_time=now_ms,
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

    cursor = await _compute_server_cursor(db, current_user.id)

    return SyncStatusResponse(
        last_sync_timestamp=ts,
        total_entries=entries_count.scalar_one() or 0,
        total_medications=meds_count.scalar_one() or 0,
        server_cursor=cursor,
        capabilities=["sync.upload.v1", "sync.push.v2", "sync.pull.v2", "sync.tombstone.v1", "sync.conflict.v1"],
    )


@router.delete("/clear-data")
async def clear_user_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete ALL data belonging to the current user (health, medication, memory, sync)."""
    uid = current_user.id

    # Order matters: delete children before parents (or rely on CASCADE)
    await db.execute(delete(SyncTombstoneRecord).where(SyncTombstoneRecord.user_id == uid))
    await db.execute(delete(MemoryEntry).where(MemoryEntry.user_id == uid))
    await db.execute(delete(MedicationEvent).where(MedicationEvent.user_id == uid))
    await db.execute(delete(InsightReport).where(InsightReport.user_id == uid))

    # HealthEntry children (QuestionResponse, DailyAdvice, DailySummary, AdviceTracking)
    # are CASCADE-deleted via FK, but explicit delete is safer for bulk ops
    entry_ids_q = select(HealthEntry.id).where(HealthEntry.user_id == uid)
    await db.execute(delete(AdviceTracking).where(AdviceTracking.entry_id.in_(entry_ids_q)))
    await db.execute(delete(DailySummary).where(DailySummary.entry_id.in_(entry_ids_q)))
    await db.execute(delete(DailyAdvice).where(DailyAdvice.entry_id.in_(entry_ids_q)))
    await db.execute(delete(QuestionResponse).where(QuestionResponse.entry_id.in_(entry_ids_q)))
    await db.execute(delete(HealthEntry).where(HealthEntry.user_id == uid))

    # Medication + courses/reminders (CASCADE via FK)
    await db.execute(delete(Medication).where(Medication.user_id == uid))

    await db.commit()

    # Clear Redis short-term chat memory for this user (best-effort).
    cleared_sessions = 0
    try:
        memory_mgr = get_memory_manager()
        cleared_sessions = await memory_mgr.short_term.clear_user_sessions(str(uid))
    except Exception:
        pass

    return {"status": "ok", "message": "所有用户数据已清除", "cleared_sessions": str(cleared_sessions)}
