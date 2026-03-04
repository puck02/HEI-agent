"""
Chat API — unified agent conversation endpoint.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import run_agent
from app.auth.router import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message to the AI health agent."""
    session_id = req.session_id or f"s-{uuid.uuid4().hex[:12]}"

    try:
        result = await run_agent(
            user_id=str(current_user.id),
            session_id=session_id,
            message=req.message,
        )
        return ChatResponse(
            answer=result["response"],
            session_id=result["session_id"],
            agent_used=result.get("agent_used"),
            model_used=result.get("model_used"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {e}")
