"""
Chat API — unified agent conversation endpoint using ChatAgent (ReAct + Tools).

Replaces the old Pipeline architecture with a single ChatAgent ReAct loop.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.chat_agent import ChatAgent
from app.auth.router import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse, StreamEvent

router = APIRouter(prefix="/chat", tags=["chat"])
log = structlog.get_logger(__name__)

# Singleton ChatAgent instance
_chat_agent: ChatAgent | None = None


def get_chat_agent() -> ChatAgent:
    global _chat_agent
    if _chat_agent is None:
        _chat_agent = ChatAgent()
    return _chat_agent


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


def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


async def _run_chat_agent(
    req: ChatRequest,
    current_user: User,
    session_id: str,
    progress_cb=None,
) -> dict:
    """Run chat through the ChatAgent ReAct loop."""
    started_at = time.perf_counter()
    agent = get_chat_agent()
    user_id = str(current_user.id)

    if progress_cb:
        await progress_cb({
            "stage": "start",
            "message": "开始处理请求",
            "elapsed_ms": _elapsed_ms(started_at),
        })

    result = await agent.chat(
        user_id=user_id,
        session_id=session_id,
        message=req.message,
        conversation_history=None,  # History managed externally for now
    )

    if progress_cb:
        await progress_cb({
            "stage": "done",
            "message": "推理完成",
            "elapsed_ms": _elapsed_ms(started_at),
            "meta": {
                "tool_calls": result.get("tool_calls_made", []),
                "iterations": result.get("iterations", 0),
            },
        })

    return {
        "answer": result["answer"],
        "session_id": session_id,
        "agent_used": "chat_agent_react",
        "model_used": "",
        "response_time_ms": result.get("latency_ms", _elapsed_ms(started_at)),
        "trace": [],
        "references": None,
    }


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message to the AI health agent (ReAct + Tools)."""
    session_id = req.session_id or f"s-{uuid.uuid4().hex[:12]}"

    try:
        result = await _run_chat_agent(req, current_user, session_id)
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
            _run_chat_agent(
                req=req,
                current_user=current_user,
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
