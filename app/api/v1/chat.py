"""
Chat API — unified agent conversation endpoint.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.orchestrator import run_agent
from app.auth.router import get_current_user
from app.database import get_db
from app.memory.manager import get_memory_manager
from app.models.health_data import HealthEntry, QuestionResponse
from app.models.medication import Medication, MedicationCourse
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


async def _build_health_context(db: AsyncSession, user_id: uuid.UUID) -> str:
    """Query recent health entries and format as context string."""
    since = date.today() - timedelta(days=7)
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


async def _build_medication_context(db: AsyncSession, user_id: uuid.UUID) -> str:
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


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message to the AI health agent."""
    session_id = req.session_id or f"s-{uuid.uuid4().hex[:12]}"

    try:
        # Build real context from DB
        health_context = await _build_health_context(db, current_user.id)
        medication_context = await _build_medication_context(db, current_user.id)

        # Recall long-term memory
        memory_mgr = get_memory_manager()
        memory_ctx = await memory_mgr.recall(
            db=db,
            user_id=current_user.id,
            session_id=session_id,
            query=req.message,
        )

        result = await run_agent(
            user_id=str(current_user.id),
            session_id=session_id,
            message=req.message,
            health_context=health_context,
            medication_context=medication_context,
            memory_override=memory_ctx,
        )

        # Extract and store long-term insights in background
        try:
            conversation = f"用户: {req.message}\n助手: {result['response']}"
            await memory_mgr.extract_and_store_insights(
                db=db, user_id=current_user.id, conversation_text=conversation
            )
        except Exception:
            pass  # non-critical

        return ChatResponse(
            answer=result["response"],
            session_id=result["session_id"],
            agent_used=result.get("agent_used"),
            model_used=result.get("model_used"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {e}")
