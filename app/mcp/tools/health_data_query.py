"""
Health data query tool — retrieve user's historical health metrics from PostgreSQL.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import structlog
from sqlalchemy import select, and_

log = structlog.get_logger(__name__)

# Metric → question_id mapping (matches HElDairy question IDs)
METRIC_QUESTION_MAP = {
    "headache": "headache_intensity",
    "neck_shoulder": "neck_shoulder_intensity",
    "stomach": "stomach_intensity",
    "nose_throat": "nose_throat_intensity",
    "knee": "knee_intensity",
    "mood": "mood_irritability",
    "sleep": "sleep_duration",
    "steps": "steps",
    "cold": "caught_cold",
    "medication_adherence": "med_on_time",
}


async def query_health_data(
    user_id: str,
    metric: str | None = None,
    days: int = 7,
) -> str:
    """
    Query user's historical health data from the database.

    This runs within the Agent context where a DB session is available.
    For standalone MCP tool calls, it returns a formatted summary.
    """
    try:
        # Import here to avoid circular imports
        from app.database import async_session_factory
        from app.models.health_data import HealthEntry, QuestionResponse

        uid = uuid.UUID(user_id)
        cutoff = date.today() - timedelta(days=days)

        async with async_session_factory() as session:
            # Get entries in date range
            stmt = (
                select(HealthEntry)
                .where(
                    and_(
                        HealthEntry.user_id == uid,
                        HealthEntry.entry_date >= cutoff,
                    )
                )
                .order_by(HealthEntry.entry_date.desc())
            )
            result = await session.execute(stmt)
            entries = result.scalars().all()

            if not entries:
                return f"最近 {days} 天没有健康记录数据。"

            # If specific metric requested, filter responses
            if metric and metric in METRIC_QUESTION_MAP:
                question_id = METRIC_QUESTION_MAP[metric]
                lines = [f"📊 最近 {days} 天「{metric}」数据："]
                for entry in entries:
                    resp_stmt = (
                        select(QuestionResponse)
                        .where(
                            and_(
                                QuestionResponse.entry_id == entry.id,
                                QuestionResponse.question_id == question_id,
                            )
                        )
                    )
                    resp_result = await session.execute(resp_stmt)
                    response = resp_result.scalar_one_or_none()
                    if response:
                        label = response.answer_label or response.answer_value or "N/A"
                        lines.append(f"  {entry.entry_date}: {label}")
                return "\n".join(lines)

            # General summary
            lines = [f"📊 最近 {days} 天健康数据概览（共 {len(entries)} 条记录）："]
            for entry in entries[:7]:  # Limit output
                lines.append(f"  📅 {entry.entry_date}")
            if len(entries) > 7:
                lines.append(f"  ... 还有 {len(entries) - 7} 条记录")
            return "\n".join(lines)

    except Exception as e:
        log.error("health_data_query_error", error=str(e))
        return f"查询健康数据失败: {e}"
