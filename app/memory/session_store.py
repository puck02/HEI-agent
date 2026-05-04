"""
Session store — in-memory session and message storage for demo mode.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog

log = structlog.get_logger(__name__)


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}

    def create_session(self, title: str | None = None) -> dict:
        session_id = f"s-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        session = {
            "session_id": session_id,
            "title": title or "新对话",
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        self._sessions[session_id] = session
        log.info("session_created", session_id=session_id)
        return session

    def get_session(self, session_id: str) -> dict | None:
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[dict]:
        sessions = sorted(
            self._sessions.values(),
            key=lambda s: s["updated_at"],
            reverse=True,
        )
        return [
            {
                "session_id": s["session_id"],
                "title": s["title"],
                "created_at": s["created_at"],
                "updated_at": s["updated_at"],
                "message_count": len(s["messages"]),
            }
            for s in sessions
        ]

    def update_session(self, session_id: str, title: str | None = None) -> dict | None:
        session = self._sessions.get(session_id)
        if not session:
            return None
        if title is not None:
            session["title"] = title
        session["updated_at"] = datetime.now(timezone.utc).isoformat()
        return session

    def delete_session(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            log.info("session_deleted", session_id=session_id)
            return True
        return False

    def add_message(self, session_id: str, role: str, content: str) -> dict | None:
        session = self._sessions.get(session_id)
        if not session:
            return None
        now = datetime.now(timezone.utc).isoformat()
        message = {
            "role": role,
            "content": content,
            "timestamp": now,
        }
        session["messages"].append(message)
        session["updated_at"] = now

        if role == "user" and session["title"] == "新对话":
            session["title"] = content[:20] + ("..." if len(content) > 20 else "")

        return message

    def get_messages(self, session_id: str) -> list[dict]:
        session = self._sessions.get(session_id)
        if not session:
            return []
        return session["messages"]


# Singleton
_instance: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _instance
    if _instance is None:
        _instance = SessionStore()
    return _instance
