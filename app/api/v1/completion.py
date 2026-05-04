"""Completion API — unified LLM entry point.

Provides a single /completion endpoint that routes to FastPipeline or
AgentPipeline based on the requested mode (or auto-detection).
"""

from __future__ import annotations

import asyncio
import time
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import run_agent
from app.auth.router import get_current_user
from app.config import get_settings
from app.context.assembler import ContextAssembler
from app.database import get_db
from app.models.user import User
from app.pipelines.agent_pipeline import AgentPipeline
from app.pipelines.base import AgentContext
from app.pipelines.fast_pipeline import FastPipeline
from app.schemas.completion import CompletionRequest, CompletionResponse

router = APIRouter(prefix="/completion", tags=["completion"])
log = structlog.get_logger(__name__)

# Thresholds for auto mode
_AUTO_MESSAGE_LENGTH_THRESHOLD = 120  # Longer messages → agent mode


def _should_use_agent_mode(message: str) -> bool:
    """Heuristic for auto mode: decide fast vs agent pipeline.

    Uses message length and keyword signals. Agent mode is used when
    the query is complex enough to benefit from reflection.
    """
    if len(message) > _AUTO_MESSAGE_LENGTH_THRESHOLD:
        return True

    # Multi-part questions or analysis requests
    complex_signals = ["分析", "对比", "趋势", "报告", "总结", "建议", "方案"]
    return any(signal in message for signal in complex_signals)


async def _run_pipeline(
    req: CompletionRequest,
    current_user: User,
    db: AsyncSession,
    session_id: str,
) -> dict:
    """Execute the appropriate pipeline based on mode."""
    settings = get_settings()
    started_at = time.perf_counter()

    # Determine mode
    if req.mode == "auto":
        use_agent = _should_use_agent_mode(req.message)
    else:
        use_agent = req.mode == "agent"

    actual_mode = "agent" if use_agent else "fast"

    assembler = ContextAssembler(db=db)
    ctx = AgentContext(
        user_id=str(current_user.id),
        session_id=session_id,
        user_message=req.message,
    )
    await ctx.load(assembler)

    log.info(
        "completion_start",
        user_id=str(current_user.id),
        mode=actual_mode,
        message_len=len(req.message),
    )

    try:
        if use_agent:
            pipeline = AgentPipeline(assembler=assembler)
        else:
            pipeline = FastPipeline(assembler=assembler)

        result = await asyncio.wait_for(
            pipeline.execute(ctx),
            timeout=settings.chat_pipeline_timeout_seconds,
        )
    except asyncio.TimeoutError:
        log.error("completion_timeout", mode=actual_mode, user_id=str(current_user.id))
        return {
            "answer": "处理超时，请稍后重试或缩短您的问题。",
            "mode_used": actual_mode,
            "agent_used": "timeout_fallback",
            "model_used": "",
            "response_time_ms": int((time.perf_counter() - started_at) * 1000),
        }

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)

    return {
        "answer": result.get("response", ""),
        "mode_used": actual_mode,
        "agent_used": result.get("agent_used"),
        "model_used": result.get("model_used"),
        "response_time_ms": elapsed_ms,
        "reflection_scores": result.get("reflection_scores", {}),
        "trace": result.get("trace", []),
    }


@router.post("", response_model=CompletionResponse)
async def completion(
    req: CompletionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unified LLM completion endpoint.

    Routes to FastPipeline or AgentPipeline based on req.mode:
    - 'fast': Single LLM call, fastest response (3-15s)
    - 'agent': Full LangGraph with intent classification + reflection (10-30s)
    - 'auto': System decides based on message complexity
    """
    session_id = req.session_id or f"s-{uuid.uuid4().hex[:12]}"

    try:
        result = await _run_pipeline(req, current_user, db, session_id)
        return CompletionResponse(session_id=session_id, **result)
    except HTTPException:
        raise
    except Exception as e:
        log.error("completion_error", error=str(e), user_id=str(current_user.id))
        raise HTTPException(status_code=500, detail="处理失败，请稍后重试")
