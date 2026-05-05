"""
Completion API — unified LLM entry point using ChatAgent (ReAct + Tools).
"""

from __future__ import annotations

import time
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.chat_agent import ChatAgent
from app.auth.router import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.completion import CompletionRequest, CompletionResponse

router = APIRouter(prefix="/completion", tags=["completion"])
log = structlog.get_logger(__name__)

# Singleton ChatAgent instance
_agent: ChatAgent | None = None


def _get_agent() -> ChatAgent:
    global _agent
    if _agent is None:
        _agent = ChatAgent()
    return _agent


@router.post("", response_model=CompletionResponse)
async def completion(
    req: CompletionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unified LLM completion endpoint using ChatAgent (ReAct + Tools)."""
    session_id = req.session_id or f"s-{uuid.uuid4().hex[:12]}"
    started_at = time.perf_counter()

    try:
        agent = _get_agent()
        result = await agent.chat(
            user_id=str(current_user.id),
            session_id=session_id,
            message=req.message,
        )

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        return CompletionResponse(
            session_id=session_id,
            answer=result["answer"],
            mode_used="react",
            agent_used="chat_agent",
            model_used="",
            response_time_ms=elapsed_ms,
        )
    except HTTPException:
        raise
    except Exception as e:
        log.error("completion_error", error=str(e), user_id=str(current_user.id))
        raise HTTPException(status_code=500, detail="处理失败，请稍后重试")
