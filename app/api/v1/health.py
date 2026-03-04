"""
Health API — daily advice, follow-up questions, weekly insights.

These endpoints are designed for direct Android integration,
maintaining 100% schema compatibility with existing HElDairy code.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.health_advisor import (
    generate_daily_advice,
    generate_follow_up_questions,
)
from app.agents.insight_analyst import generate_weekly_insight
from app.auth.router import get_current_user
from app.database import get_db
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


@router.post("/daily-advice", response_model=DailyAdviceResponse)
async def daily_advice(
    req: DailyAdviceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate daily lifestyle advice — replaces Android DeepSeekClient.fetchAdvice()."""
    try:
        result = await generate_daily_advice(
            today_answers=req.today_answers,
            summary_7d=req.summary_7d,
            active_meds=req.active_meds_summary,
            adherence_hint=req.adherence_hint,
        )
        return DailyAdviceResponse(
            observations=result.get("observations", []),
            actions=result.get("actions", []),
            tomorrow_focus=result.get("tomorrow_focus", []),
            red_flags=result.get("red_flags", []),
            model=result.get("model"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Advice generation failed: {e}")


@router.post("/follow-up", response_model=FollowUpResponse)
async def follow_up(
    req: FollowUpRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate adaptive follow-up questions — replaces DeepSeekClient.fetchFollowUpQuestions()."""
    try:
        result = await generate_follow_up_questions(
            today_answers=req.today_answers,
            summary_7d=req.summary_7d,
            triggered_symptoms=req.triggered_symptoms,
        )
        questions = [
            FollowUpQuestion(**q) for q in result.get("questions", [])
        ]
        return FollowUpResponse(questions=questions, model=result.get("model"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Follow-up generation failed: {e}")


@router.post("/weekly-insight", response_model=WeeklyInsightResponse)
async def weekly_insight(
    req: WeeklyInsightRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate weekly health insight — replaces DeepSeekClient.fetchWeeklyInsight()."""
    try:
        result = await generate_weekly_insight(
            week_start=req.week_start_date,
            week_end=req.week_end_date,
            summary_7d=req.summary_7d,
            summary_30d=req.summary_30d,
            active_meds=req.active_meds_summary,
        )
        return WeeklyInsightResponse(
            schema_version=result.get("schemaVersion", 1),
            week_start_date=req.week_start_date,
            week_end_date=req.week_end_date,
            summary=result.get("summary", ""),
            highlights=result.get("highlights", []),
            suggestions=result.get("suggestions", []),
            cautions=result.get("cautions", []),
            confidence=result.get("confidence", "medium"),
            model=result.get("model"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insight generation failed: {e}")
