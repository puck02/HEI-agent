"""
Health API — daily advice, follow-up questions, weekly insights.

Refactored to use the Service layer directly instead of old agents.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.router import get_current_user
from app.database import get_db
from app.llm.router import get_llm_router
from app.models.user import User
from app.schemas.health import (
    DailyAdviceRequest,
    DailyAdviceResponse,
    FollowUpRequest,
    FollowUpResponse,
    FollowUpQuestion,
    WeeklyInsightRequest,
    WeeklyInsightResponse,
)

router = APIRouter(prefix="/health", tags=["health"])


def _build_health_prompt(today_answers: dict, summary_7d: dict | None,
                          active_meds: list[str] | None, adherence_hint: str | None) -> str:
    """Build a prompt for health advice generation."""
    parts = ["请根据以下用户健康数据生成每日建议：", f"\n今日数据：{today_answers}"]
    if summary_7d:
        parts.append(f"\n近7日趋势：{summary_7d}")
    if active_meds:
        parts.append(f"\n当前用药：{', '.join(active_meds)}")
    if adherence_hint:
        parts.append(f"\n用药依从性：{adherence_hint}")
    parts.append("\n请返回 JSON，包含 observations(观察), actions(建议行动), tomorrow_focus(明日重点), red_flags(预警)。")
    return "\n".join(parts)


def _build_followup_prompt(today_answers: dict, summary_7d: dict | None,
                            triggered_symptoms: list[str]) -> str:
    """Build a prompt for follow-up question generation."""
    parts = ["根据以下用户健康数据生成1-3个追问：", f"\n今日数据：{today_answers}"]
    if summary_7d:
        parts.append(f"\n近7日趋势：{summary_7d}")
    if triggered_symptoms:
        parts.append(f"\n触发症状：{', '.join(triggered_symptoms)}")
    parts.append("\n请返回 JSON，包含 questions 数组，每项有 text, type(choice/slider), options(可选)。")
    return "\n".join(parts)


@router.post("/daily-advice", response_model=DailyAdviceResponse)
async def daily_advice(
    req: DailyAdviceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate daily lifestyle advice."""
    try:
        router = get_llm_router()
        prompt = _build_health_prompt(
            req.today_answers, req.summary_7d,
            req.active_meds_summary, req.adherence_hint,
        )
        result = await router.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )
        import json
        data = json.loads(result.content)
        return DailyAdviceResponse(
            observations=data.get("observations", []),
            actions=data.get("actions", []),
            tomorrow_focus=data.get("tomorrow_focus", []),
            red_flags=data.get("red_flags", []),
            model=result.model,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Advice generation failed: {e}")


@router.post("/follow-up", response_model=FollowUpResponse)
async def follow_up(
    req: FollowUpRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate adaptive follow-up questions."""
    try:
        router = get_llm_router()
        prompt = _build_followup_prompt(
            req.today_answers, req.summary_7d, req.triggered_symptoms,
        )
        result = await router.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=512,
            response_format={"type": "json_object"},
        )
        import json
        data = json.loads(result.content)
        questions = [
            FollowUpQuestion(**q) for q in data.get("questions", [])
        ]
        return FollowUpResponse(questions=questions, model=result.model)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Follow-up generation failed: {e}")


@router.post("/weekly-insight", response_model=WeeklyInsightResponse)
async def weekly_insight(
    req: WeeklyInsightRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate weekly health insight."""
    try:
        router = get_llm_router()
        prompt = (
            f"请根据以下用户健康数据生成本周洞察：\n"
            f"周范围：{req.week_start_date} ~ {req.week_end_date}\n"
            f"7日数据：{req.summary_7d}\n"
            f"30日趋势：{req.summary_30d or '无'}\n"
            f"当前用药：{req.active_meds_summary or []}\n"
            f"请返回 JSON，包含 summary(总结), highlights(亮点), suggestions(建议), cautions(注意事项), confidence(low/medium/high)。"
        )
        result = await router.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )
        import json
        data = json.loads(result.content)
        return WeeklyInsightResponse(
            week_start_date=req.week_start_date,
            week_end_date=req.week_end_date,
            summary=data.get("summary", ""),
            highlights=data.get("highlights", []),
            suggestions=data.get("suggestions", []),
            cautions=data.get("cautions", []),
            confidence=data.get("confidence", "medium"),
            model=result.model,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insight generation failed: {e}")
