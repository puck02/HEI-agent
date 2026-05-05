from __future__ import annotations

import logging

from app.services.health_log_service import HealthLogService

log = logging.getLogger(__name__)


async def get_health_logs(user_id: str, days: int = 7) -> str:
    service = HealthLogService()
    try:
        records = service.get_logs(user_id, days)
        if not records:
            return f"No health logs in the past {days} day(s)."
        lines = []
        for r in records:
            lines.append(f"- [{r['entry_date']}] {r.get('data', '')}")
        return f"Health logs (past {days} day(s)):\n" + "\n".join(lines)
    except Exception:
        log.exception("get_health_logs_failed user_id=%s", user_id)
        return "Failed to retrieve health logs."


async def log_health(user_id: str, entry_date: str = "", data: str = "") -> str:
    service = HealthLogService()
    try:
        log_id = service.log_health(user_id, {
            "entry_date": entry_date,
            "data": data,
        })
        return f"Health log recorded (id={log_id})."
    except Exception:
        log.exception("log_health_failed user_id=%s", user_id)
        return "Failed to log health entry."
