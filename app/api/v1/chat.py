"""
Chat API — unified agent conversation endpoint.

Optimized fast-path: single LLM call with all context pre-loaded.
Smart retrieval: always fetches long-term memory, conditionally fetches RAG knowledge.
No intent classification → no ReAct → no reflection → fast response.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import date, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.orchestrator import run_chat
from app.auth.router import get_current_user
from app.database import async_session_factory, get_db
from app.memory.manager import get_memory_manager
from app.models.health_data import HealthEntry, QuestionResponse
from app.models.medication import Medication, MedicationCourse
from app.models.user import User
from app.rag.engine import get_rag_engine
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])
log = structlog.get_logger(__name__)

# Keywords that trigger RAG knowledge base retrieval
_RAG_KEYWORDS = re.compile(
    r"(健康|症状|疼痛|头痛|失眠|睡眠|血压|血糖|心率|体重|运动|饮食|营养|"
    r"药|用药|服药|剂量|副作用|中医|养生|穴位|食疗|调理|"
    r"疾病|感冒|发烧|咳嗽|过敏|炎症|焦虑|抑郁|压力|疲劳|"
    r"维生素|蛋白质|碳水|脂肪|膳食|忌口|禁忌|怎么办|怎么治|如何缓解)",
    re.IGNORECASE,
)


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


async def _background_memorize(
    user_id: uuid.UUID,
    session_id: str,
    user_message: str,
    assistant_response: str,
) -> None:
    """Background task: save to short-term memory and extract long-term insights."""
    try:
        memory_mgr = get_memory_manager()
        # Save to Redis short-term memory
        await memory_mgr.short_term.add_message(session_id, "user", user_message)
        await memory_mgr.short_term.add_message(session_id, "assistant", assistant_response)
    except Exception as e:
        log.warning("bg_short_term_save_failed", error=str(e))

    # Extract and store long-term insights (uses its own DB session)
    try:
        memory_mgr = get_memory_manager()
        async with async_session_factory() as db:
            conversation = f"用户: {user_message}\n助手: {assistant_response}"
            await memory_mgr.extract_and_store_insights(
                db=db, user_id=user_id, conversation_text=conversation
            )
            await db.commit()
    except Exception as e:
        log.warning("bg_insight_extraction_failed", error=str(e))


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message to the AI health agent (fast path)."""
    session_id = req.session_id or f"s-{uuid.uuid4().hex[:12]}"

    try:
        memory_mgr = get_memory_manager()

        # 1. Build context from DB + long-term memory + optional RAG (all parallel)
        #    Long-term memory is always fetched (cheap: ~200ms embedding + DB query).
        #    RAG knowledge base is fetched only when the message contains health/med keywords.
        need_rag = bool(_RAG_KEYWORDS.search(req.message))

        async def _fetch_long_term_memories() -> list[str]:
            """Fetch semantically relevant long-term memories for this user."""
            try:
                result = await memory_mgr.recall(
                    db=db,
                    user_id=current_user.id,
                    session_id=session_id,
                    query=req.message,
                    top_k=5,
                )
                return result.get("relevant_memories", [])
            except Exception as e:
                log.warning("long_term_recall_failed", error=str(e))
                return []

        async def _fetch_rag_context() -> str:
            """Fetch relevant knowledge from RAG (Qdrant) if needed."""
            if not need_rag:
                return ""
            try:
                rag = get_rag_engine()
                return await rag.retrieve_as_context(
                    query=req.message,
                    top_k=3,
                )
            except Exception as e:
                log.warning("rag_retrieval_failed", error=str(e))
                return ""

        health_ctx, med_ctx, long_term_memories, knowledge_ctx = await asyncio.gather(
            _build_health_context(db, current_user.id),
            _build_medication_context(db, current_user.id),
            _fetch_long_term_memories(),
            _fetch_rag_context(),
        )

        # 2. Get conversation history from Redis (fast, no embedding call)
        conversation_history = ""
        try:
            conversation_history = await memory_mgr.short_term.get_formatted_history(session_id)
        except Exception:
            pass  # Redis down → skip history, not critical

        log.info(
            "chat_context_loaded",
            user_id=str(current_user.id),
            has_health=bool(health_ctx),
            has_med=bool(med_ctx),
            long_term_count=len(long_term_memories),
            has_rag=bool(knowledge_ctx),
            rag_triggered=need_rag,
        )

        # 3. Single fast LLM call with all context
        result = await asyncio.wait_for(
            run_chat(
                user_id=str(current_user.id),
                session_id=session_id,
                message=req.message,
                health_context=health_ctx,
                medication_context=med_ctx,
                conversation_history=conversation_history,
                long_term_memories=long_term_memories,
                knowledge_context=knowledge_ctx,
            ),
            timeout=50.0,  # 50s deadline (client readTimeout=60s)
        )

        # 4. Background: save memory + extract insights (non-blocking)
        asyncio.create_task(
            _background_memorize(
                current_user.id, session_id, req.message, result["response"]
            )
        )

        return ChatResponse(
            answer=result["response"],
            session_id=session_id,
            agent_used=result.get("agent_used"),
            model_used=result.get("model_used"),
        )

    except asyncio.TimeoutError:
        log.error("chat_timeout", user_id=str(current_user.id), message=req.message[:50])
        return ChatResponse(
            answer="🎀 哎呀，Kitty 想太久啦～请再问我一次好不好？",
            session_id=session_id,
            agent_used="timeout_fallback",
            model_used="",
        )
    except Exception as e:
        log.error("chat_error", error=str(e), user_id=str(current_user.id))
        raise HTTPException(status_code=500, detail=f"Agent error: {e}")
