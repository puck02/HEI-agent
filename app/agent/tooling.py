"""Tool runtime contracts and in-memory pending action storage.

This module keeps tool confirmation state outside ToolRegistry so write
operations can be isolated per user/session while the storage adapter remains
replaceable later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class PendingAction:
    """A write tool invocation waiting for explicit user confirmation."""

    user_id: str
    session_id: str
    tool_name: str
    args: dict[str, Any]
    action_id: str = field(default_factory=lambda: f"pending_{uuid4().hex}")
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    source: str = "llm_tool_call"

    def __post_init__(self) -> None:
        if self.expires_at is None:
            self.expires_at = self.created_at + timedelta(minutes=15)

    @property
    def key(self) -> tuple[str, str]:
        return (self.user_id, self.session_id)

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (now or datetime.now(timezone.utc)) >= self.expires_at


class InMemoryPendingActionStore:
    """Session-scoped in-memory storage for pending write actions.

    The adapter intentionally uses a small interface so it can later be swapped
    for SQLite without changing ChatAgent's confirmation flow.
    """

    def __init__(self) -> None:
        self._actions: dict[tuple[str, str], PendingAction] = {}

    async def set(self, action: PendingAction) -> PendingAction:
        self._actions[action.key] = action
        return action

    async def get(self, user_id: str, session_id: str) -> PendingAction | None:
        key = (user_id, session_id)
        action = self._actions.get(key)
        if action and action.is_expired():
            self._actions.pop(key, None)
            return None
        return action

    async def clear(self, user_id: str, session_id: str) -> PendingAction | None:
        return self._actions.pop((user_id, session_id), None)
