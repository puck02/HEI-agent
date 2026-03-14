"""
Chat API — unified agent conversation endpoint.

Optimized fast-path: single LLM call with all context pre-loaded.
Smart retrieval: always fetches long-term memory, conditionally fetches RAG knowledge.
No intent classification → no ReAct → no reflection → fast response.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import date, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.orchestrator import run_chat
from app.auth.router import get_current_user
from app.config import get_settings
from app.database import async_session_factory, get_db
from app.memory.manager import get_memory_manager
from app.models.health_data import HealthEntry, QuestionResponse
from app.models.medication import Medication, MedicationCourse
from app.models.user import User
from app.rag.engine import get_rag_engine
from app.schemas.chat import ChatRequest, ChatResponse, StreamEvent

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


def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


async def _run_chat_pipeline(
    req: ChatRequest,
    current_user: User,
    db: AsyncSession,
    session_id: str,
    progress_cb: Callable[[dict], Awaitable[None]] | None = None,
) -> dict:
    """Run chat pipeline and optionally emit progress events."""
    started_at = time.perf_counter()
    settings = get_settings()
    trace: list[dict] = []

    async def _emit(stage: str, message: str, meta: dict | None = None) -> None:
        event = {
            "stage": stage,
            "message": message,
            "elapsed_ms": _elapsed_ms(started_at),
        }
        if meta:
            event["meta"] = meta
        trace.append(event)
        if progress_cb:
            await progress_cb(event)

    await _emit("start", "开始处理请求")
    memory_mgr = get_memory_manager()

    # Track user-session relation for later user-level cleanup.
    try:
        await memory_mgr.short_term.register_session(str(current_user.id), session_id)
    except Exception as e:
        log.warning("register_chat_session_failed", error=str(e))

    await _emit("context", "正在加载健康数据、用药和记忆")

    # Long-term memory is always fetched. RAG is conditional by keyword hit.
    need_rag = bool(_RAG_KEYWORDS.search(req.message))
    need_heavy_context = need_rag or len(req.message.strip()) > 6

    async def _fetch_long_term_memories() -> list[str]:
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

    async def _fetch_health_context() -> str:
        if not need_heavy_context:
            return ""
        return await _build_health_context(db, current_user.id)

    async def _fetch_medication_context() -> str:
        if not need_heavy_context:
            return ""
        return await _build_medication_context(db, current_user.id)

    health_ctx, med_ctx, long_term_memories, knowledge_ctx = await asyncio.gather(
        _fetch_health_context(),
        _fetch_medication_context(),
        _fetch_long_term_memories(),
        _fetch_rag_context(),
    )

    conversation_history = ""
    try:
        # Keep short history compact to lower prompt size and improve latency.
        conversation_history = await memory_mgr.short_term.get_formatted_history(
            session_id,
            max_messages=settings.chat_history_max_messages,
            max_chars=settings.chat_history_max_chars,
        )
    except Exception:
        pass

    log.info(
        "chat_context_loaded",
        user_id=str(current_user.id),
        has_health=bool(health_ctx),
        has_med=bool(med_ctx),
        long_term_count=len(long_term_memories),
        has_rag=bool(knowledge_ctx),
        rag_triggered=need_rag,
        history_chars=len(conversation_history),
    )

    await _emit(
        "context_ready",
        "上下文加载完成，正在推理",
        {
            "has_health": bool(health_ctx),
            "has_medication": bool(med_ctx),
            "long_term_count": len(long_term_memories),
            "rag_used": bool(knowledge_ctx),
        },
    )

    try:
        # Tighten end-to-end deadline so user gets faster fallback instead of long blocking.
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
            timeout=settings.chat_pipeline_timeout_seconds,
        )
    except asyncio.TimeoutError:
        log.error("chat_timeout", user_id=str(current_user.id), message=req.message[:50])
        await _emit("timeout", "推理超时，已返回兜底响应")
        return {
            "answer": "🎀 哎呀，Kitty 想太久啦～请再问我一次好不好？",
            "session_id": session_id,
            "agent_used": "timeout_fallback",
            "model_used": "",
            "response_time_ms": _elapsed_ms(started_at),
            "trace": trace,
        }

    await _emit(
        "llm_done",
        "推理完成，正在整理回复",
        {
            "agent_used": result.get("agent_used"),
            "model_used": result.get("model_used"),
            "tools_called": result.get("tools_called", []),
        },
    )

    asyncio.create_task(
        _background_memorize(
            current_user.id, session_id, req.message, result["response"]
        )
    )
    await _emit("finalize", "已完成响应并异步保存记忆")

    return {
        "answer": result["response"],
        "session_id": session_id,
        "agent_used": result.get("agent_used"),
        "model_used": result.get("model_used"),
        "response_time_ms": _elapsed_ms(started_at),
        "trace": trace,
    }


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message to the AI health agent (fast path)."""
    session_id = req.session_id or f"s-{uuid.uuid4().hex[:12]}"

    try:
        result = await _run_chat_pipeline(req, current_user, db, session_id)
        return ChatResponse(**result)
    except Exception as e:
        log.error("chat_error", error=str(e), user_id=str(current_user.id))
        raise HTTPException(status_code=500, detail=f"Agent error: {e}")


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE chat endpoint with rolling progress events and final response."""
    session_id = req.session_id or f"s-{uuid.uuid4().hex[:12]}"

    async def event_generator():
        queue: asyncio.Queue[dict] = asyncio.Queue()

        async def _push_progress(event: dict) -> None:
            await queue.put(StreamEvent(event="progress", data=event).model_dump())

        task = asyncio.create_task(
            _run_chat_pipeline(
                req=req,
                current_user=current_user,
                db=db,
                session_id=session_id,
                progress_cb=_push_progress,
            )
        )

        while True:
            if task.done() and queue.empty():
                break

            try:
                next_event = await asyncio.wait_for(queue.get(), timeout=0.2)
                yield (
                    f"event: {next_event['event']}\n"
                    f"data: {json.dumps(next_event['data'], ensure_ascii=False)}\n\n"
                )
            except asyncio.TimeoutError:
                continue

        try:
            result = await task
            done_payload = {
                "answer": result["answer"],
                "session_id": result["session_id"],
                "agent_used": result.get("agent_used"),
                "model_used": result.get("model_used"),
                "response_time_ms": result.get("response_time_ms"),
            }
            done_event = StreamEvent(event="done", data=done_payload).model_dump()
            yield (
                f"event: {done_event['event']}\n"
                f"data: {json.dumps(done_event['data'], ensure_ascii=False)}\n\n"
            )
        except Exception as e:
            log.error("chat_stream_error", error=str(e), user_id=str(current_user.id))
            err_msg = str(e).strip() or "聊天处理失败，请稍后重试"
            error_event = StreamEvent(
                event="error",
                data={
                    "message": err_msg,
                    "session_id": session_id,
                },
            ).model_dump()
            yield (
                f"event: {error_event['event']}\n"
                f"data: {json.dumps(error_event['data'], ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
