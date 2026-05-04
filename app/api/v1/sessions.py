"""
Sessions API — CRUD endpoints for conversation session management.

Demo mode: no authentication required.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException

from app.memory.session_store import get_session_store
from app.schemas.session import (
    SessionCreate,
    SessionDetailOut,
    SessionListOut,
    SessionOut,
    SessionUpdate,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])
log = structlog.get_logger(__name__)


@router.post("", response_model=SessionDetailOut)
async def create_session(req: SessionCreate | None = None):
    """Create a new conversation session."""
    store = get_session_store()
    title = req.title if req else None
    session = store.create_session(title=title)
    return SessionDetailOut(**session)


@router.get("", response_model=SessionListOut)
async def list_sessions():
    """List all sessions (metadata only, no messages)."""
    store = get_session_store()
    sessions = store.list_sessions()
    return SessionListOut(sessions=[SessionOut(**s) for s in sessions])


@router.get("/{session_id}", response_model=SessionDetailOut)
async def get_session(session_id: str):
    """Get a single session with full message history."""
    store = get_session_store()
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return SessionDetailOut(**session)


@router.put("/{session_id}", response_model=SessionDetailOut)
async def update_session(session_id: str, req: SessionUpdate):
    """Update a session (e.g., rename title)."""
    store = get_session_store()
    session = store.update_session(session_id, title=req.title)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return SessionDetailOut(**session)


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    store = get_session_store()
    if not store.delete_session(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"success": True}
