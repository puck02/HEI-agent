"""
Session management — in-memory session store for demo mode.
"""

from app.sessions.manager import SessionManager, get_session_manager

__all__ = ["SessionManager", "get_session_manager"]
