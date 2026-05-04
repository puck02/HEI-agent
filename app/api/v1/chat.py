"""
Chat API — unified agent conversation endpoint.

Uses the new Pipeline architecture:
- ContextAssembler: loads all data sources in parallel
- FastPipeline: single LLM call with all context pre-loaded
- AgentPipeline: full LangGraph orchestration (via orchestrator.run_agent)

Smart retrieval: always fetches long-term memory, conditionally fetches RAG knowledge.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import date, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import run_agent
from app.auth.router import get_current_user
from app.config import get_settings
from app.context.assembler import ContextAssembler
from app.database import async_session_factory, get_db
from app.memory.manager import get_memory_manager
from app.models.user import User
from app.pipelines.base import AgentContext
from app.pipelines.fast_pipeline import FastPipeline
from app.schemas.chat import ChatRequest, ChatResponse, StreamEvent

router = APIRouter(prefix="/chat", tags=["chat"])
log = structlog.get_logger(__name__)


def _normalize_chat_error(exc: Exception) -> str:
    """Return a user-readable error for chat REST/SSE responses."""
    fallback = "聊天处理失败，请稍后重试"

    detail: str = ""
    if isinstance(exc, HTTPException):
        if isinstance(exc.detail, str):
            detail = exc.detail.strip()
        elif isinstance(exc.detail, dict):
            detail = (
                str(exc.detail.get("detail") or exc.detail.get("message") or "").strip()
            )
        elif exc.detail is not None:
            detail = str(exc.detail).strip()
    else:
        detail = str(exc).strip()

    if detail.lower().startswith("agent error:"):
        detail = detail[len("agent error:"):].strip()

    if detail.lower() in {"", "unknown", "unknown error", "internal server error", "none", "null"}:
        return fallback
    if detail in {"未知错误", "发生错误"}:
        return fallback
    return detail


async def _background_memorize(
    user_id: uuid.UUID,
    session_id: str,
    user_message: str,
    assistant_response: str,
) -> None:
    """Background task: save to short-term memory and extract long-term insights."""
    try:
        memory_mgr = get_memory_manager()
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
    """Run chat pipeline using the new Pipeline architecture."""
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

    # Use ContextAssembler to load all data sources in parallel
    assembler = ContextAssembler(db=db)
    ctx = AgentContext(
        user_id=str(current_user.id),
        session_id=session_id,
        user_message=req.message,
    )
    await ctx.load(assembler)

    log.info(
        "chat_context_loaded",
        user_id=str(current_user.id),
        has_health=bool(ctx.health_context),
        has_med=bool(ctx.medication_context),
        long_term_count=len(ctx.long_term_memories),
        has_rag=bool(ctx.knowledge_context),
        history_chars=len(ctx.conversation_history),
    )

    await _emit(
        "context_ready",
        "上下文加载完成，正在推理",
        {
            "has_health": bool(ctx.health_context),
            "has_medication": bool(ctx.medication_context),
            "long_term_count": len(ctx.long_term_memories),
            "rag_used": bool(ctx.knowledge_context),
        },
    )

    try:
        # Use FastPipeline for the fast path
        pipeline = FastPipeline(assembler=assembler)
        result = await asyncio.wait_for(
            pipeline.execute(ctx),
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
        "references": ctx.knowledge_refs,
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
    except HTTPException:
        raise
    except Exception as e:
        log.error("chat_error", error=str(e), user_id=str(current_user.id))
        raise HTTPException(status_code=500, detail=_normalize_chat_error(e))


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
                "references": result.get("references", []),
            }
            done_event = StreamEvent(event="done", data=done_payload).model_dump()
            yield (
                f"event: {done_event['event']}\n"
                f"data: {json.dumps(done_event['data'], ensure_ascii=False)}\n\n"
            )
        except Exception as e:
            log.error("chat_stream_error", error=str(e), user_id=str(current_user.id))
            err_msg = _normalize_chat_error(e)
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
