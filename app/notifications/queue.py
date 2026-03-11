"""Redis-backed lightweight server notification queue."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import redis.asyncio as redis

from app.config import get_settings


class NotificationQueue:
    """Stores per-user server notifications in Redis lists."""

    def __init__(self) -> None:
        settings = get_settings()
        self.redis = redis.from_url(settings.redis_url, decode_responses=True)
        self.max_items = 200
        self.ttl_seconds = 7 * 24 * 60 * 60

    def _queue_key(self, user_id: str) -> str:
        return f"notify:queue:{user_id}"

    async def enqueue(
        self,
        user_id: str,
        title: str,
        body: str,
        type_: str = "general",
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now_ms = int(time.time() * 1000)
        payload: dict[str, Any] = {
            "id": f"{now_ms}-{uuid.uuid4().hex[:8]}",
            "title": title,
            "body": body,
            "type": type_,
            "data": data or {},
            "created_at": now_ms,
        }
        key = self._queue_key(user_id)
        await self.redis.rpush(key, json.dumps(payload, ensure_ascii=False))
        await self.redis.ltrim(key, -self.max_items, -1)
        await self.redis.expire(key, self.ttl_seconds)
        return payload

    async def pull(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 100))
        key = self._queue_key(user_id)
        raw_items = await self.redis.lpop(key, safe_limit)
        if raw_items is None:
            return []

        if isinstance(raw_items, str):
            raw_list = [raw_items]
        else:
            raw_list = list(raw_items)

        notifications: list[dict[str, Any]] = []
        for item in raw_list:
            try:
                parsed = json.loads(item)
                if isinstance(parsed, dict):
                    notifications.append(parsed)
            except Exception:
                continue
        return notifications

    async def clear_user(self, user_id: str) -> None:
        await self.redis.delete(self._queue_key(user_id))

    async def close(self) -> None:
        await self.redis.aclose()


_notification_queue: NotificationQueue | None = None


def get_notification_queue() -> NotificationQueue:
    global _notification_queue
    if _notification_queue is None:
        _notification_queue = NotificationQueue()
    return _notification_queue
