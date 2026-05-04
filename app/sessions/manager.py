"""
Session manager — re-exports from app.memory.session_store for backward compatibility.
"""

from app.memory.session_store import SessionStore, get_session_store

# Backward-compatible alias
SessionManager = SessionStore
get_session_manager = get_session_store

__all__ = ["SessionManager", "get_session_manager", "SessionStore", "get_session_store"]
