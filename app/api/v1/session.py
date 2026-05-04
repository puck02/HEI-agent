"""
Session API — CRUD endpoints for conversation session management.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException

from app.schemas.session import (
    SessionCreate,
    SessionDetailOut,
    SessionListOut,
    SessionOut,
    SessionUpdate,
)
from app.sessions.manager import get_session_manager

router = APIRouter(prefix="/sessions", tags=["sessions"])
log = structlog.get_logger(__name__)


@router.post("", response_model=SessionDetailOut)
async def create_session(req: SessionCreate | None = None):
    """Create a new conversation session."""
    mgr = get_session_manager()
    title = req.title if req else None
    session = mgr.create_session(title=title)
    return SessionDetailOut(**session)


@router.get("", response_model=SessionListOut)
async def list_sessions():
    """List all sessions (metadata only, no messages)."""
    mgr = get_session_manager()
    sessions = mgr.list_sessions()
    return SessionListOut(sessions=[SessionOut(**s) for s in sessions])


@router.get("/{session_id}", response_model=SessionDetailOut)
async def get_session(session_id: str):
    """Get a single session with full message history."""
    mgr = get_session_manager()
    session = mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return SessionDetailOut(**session)


@router.put("/{session_id}", response_model=SessionDetailOut)
async def update_session(session_id: str, req: SessionUpdate):
    """Update a session (e.g., rename title)."""
    mgr = get_session_manager()
    session = mgr.update_session(session_id, title=req.title)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return SessionDetailOut(**session)


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    mgr = get_session_manager()
    if not mgr.delete_session(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"detail": "会话已删除", "session_id": session_id}
