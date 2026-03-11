"""Firebase Cloud Messaging sender and token registry."""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as redis
from firebase_admin import credentials, initialize_app, messaging
from firebase_admin import get_app as firebase_get_app

from app.config import get_settings


class PushService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.redis = redis.from_url(self.settings.redis_url, decode_responses=True)
        self._firebase_ready = False
        self._init_firebase_once()

    def _tokens_key(self, user_id: str) -> str:
        return f"push:tokens:{user_id}"

    def _token_meta_key(self, token: str) -> str:
        return f"push:token_meta:{token}"

    def _init_firebase_once(self) -> None:
        cred_path = self.settings.fcm_service_account_json
        if not cred_path:
            self._firebase_ready = False
            return

        try:
            firebase_get_app()
        except Exception:
            cred = credentials.Certificate(cred_path)
            initialize_app(cred)

        self._firebase_ready = True

    async def register_token(self, user_id: str, token: str, platform: str = "android") -> None:
        if not token:
            return
        await self.redis.sadd(self._tokens_key(user_id), token)
        await self.redis.hset(
            self._token_meta_key(token),
            mapping={"user_id": user_id, "platform": platform},
        )

    async def unregister_token(self, user_id: str, token: str) -> None:
        if not token:
            return
        await self.redis.srem(self._tokens_key(user_id), token)
        await self.redis.delete(self._token_meta_key(token))

    async def list_tokens(self, user_id: str) -> list[str]:
        result = await self.redis.smembers(self._tokens_key(user_id))
        return sorted(list(result)) if result else []

    async def send_to_user(
        self,
        user_id: str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tokens = await self.list_tokens(user_id)
        if not tokens:
            return {"sent": 0, "failed": 0, "reason": "no_tokens"}

        if not self._firebase_ready:
            return {"sent": 0, "failed": len(tokens), "reason": "fcm_not_configured"}

        payload = {k: str(v) for k, v in (data or {}).items()}
        sent = 0
        failed = 0

        for token in tokens:
            msg = messaging.Message(
                token=token,
                notification=messaging.Notification(title=title, body=body),
                data=payload,
                android=messaging.AndroidConfig(priority="high"),
            )
            try:
                messaging.send(msg)
                sent += 1
            except Exception:
                failed += 1

        return {"sent": sent, "failed": failed}

    async def close(self) -> None:
        await self.redis.aclose()


_push_service: PushService | None = None


def get_push_service() -> PushService:
    global _push_service
    if _push_service is None:
        _push_service = PushService()
    return _push_service
