"""
Medication API — NLP parse and info summary endpoints.

These endpoints replace the Android DeepSeek direct calls for medication features.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.medication_agent import (
    generate_med_info_summary,
    parse_medication_nlp,
)
from app.auth.router import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.medication import (
    MedInfoSummaryRequest,
    MedInfoSummaryResponse,
    MedNlpParseRequest,
    MedNlpParseResponse,
    MedAction,
)

router = APIRouter(prefix="/medication", tags=["medication"])


@router.post("/parse-nlp", response_model=MedNlpParseResponse)
async def parse_nlp(
    req: MedNlpParseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Parse natural language medication event — replaces Android MedicationNlpParser."""
    try:
        result = await parse_medication_nlp(
            raw_text=req.raw_text,
            current_meds=req.current_meds,
            active_courses=req.active_courses_summary,
        )
        actions = [MedAction(**a) for a in result.get("actions", [])]
        return MedNlpParseResponse(
            mentioned_meds=result.get("mentioned_meds", []),
            actions=actions,
            questions=result.get("questions", []),
            model=result.get("model"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"NLP parse failed: {e}")


@router.post("/info-summary", response_model=MedInfoSummaryResponse)
async def info_summary(
    req: MedInfoSummaryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Extract medication info summary — replaces Android MedicationInfoSummaryGenerator."""
    try:
        result = await generate_med_info_summary(
            text=req.text,
            med_name=req.med_name,
        )
        return MedInfoSummaryResponse(
            name_candidates=result.get("name_candidates", []),
            dosage_summary=result.get("dosage_summary"),
            cautions_summary=result.get("cautions_summary"),
            adverse_summary=result.get("adverse_summary"),
            model=result.get("model"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Info summary failed: {e}")
