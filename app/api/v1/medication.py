"""
Medication API — NLP parse and info summary endpoints.

Refactored to use LLM router directly instead of old medication_agent.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.router import get_current_user
from app.database import get_db
from app.llm.router import get_llm_router
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
    """Parse natural language medication event."""
    try:
        router = get_llm_router()
        prompt = (
            f"请解析以下用户输入的用药信息：\n"
            f"原文：{req.raw_text}\n"
            f"当前在用药品：{req.current_meds}\n"
            f"当前疗程：{req.active_courses_summary or '无'}\n"
            f"请返回 JSON，包含 mentioned_meds(提及的药品列表), actions(操作列表), questions(追问，最多2个)。"
            f"actions 每项包含 action_type(add_med/start_course/pause_course/end_course/update_course/noop), med_name, course_fields。"
        )
        result = await router.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )
        import json
        data = json.loads(result.content)
        actions = [MedAction(**a) for a in data.get("actions", [])]
        return MedNlpParseResponse(
            mentioned_meds=data.get("mentioned_meds", []),
            actions=actions,
            questions=data.get("questions", []),
            model=result.model,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"NLP parse failed: {e}")


@router.post("/info-summary", response_model=MedInfoSummaryResponse)
async def info_summary(
    req: MedInfoSummaryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Extract medication info summary."""
    try:
        router = get_llm_router()
        prompt = (
            f"请从以下药品信息中提取摘要：\n"
            f"药品名：{req.med_name or '未知'}\n"
            f"文本：{req.text}\n"
            f"请返回 JSON，包含 name_candidates(名称候选), dosage_summary(用法用量摘要), "
            f"cautions_summary(注意事项摘要), adverse_summary(不良反应摘要)。"
        )
        result = await router.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )
        import json
        data = json.loads(result.content)
        return MedInfoSummaryResponse(
            name_candidates=data.get("name_candidates", []),
            dosage_summary=data.get("dosage_summary"),
            cautions_summary=data.get("cautions_summary"),
            adverse_summary=data.get("adverse_summary"),
            model=result.model,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Info summary failed: {e}")
