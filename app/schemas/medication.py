"""
Medication Pydantic schemas — NLP parse, info summary.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── NLP Parse ────────────────────────────────────────────


class MedNlpParseRequest(BaseModel):
    """Natural language medication event → structured actions."""
    raw_text: str = Field(..., min_length=1, max_length=2000)
    current_meds: list[str] = Field(default_factory=list)  # names of active medications
    active_courses_summary: list[dict] | None = None


class MedAction(BaseModel):
    action_type: str  # add_med / start_course / pause_course / end_course / update_course / noop
    med_name: str
    course_fields: dict | None = None  # startDate, endDate, status, frequencyText, etc.


class MedNlpParseResponse(BaseModel):
    mentioned_meds: list[dict] = Field(default_factory=list)  # [{name, in_library: bool}]
    actions: list[MedAction] = Field(default_factory=list)
    questions: list[dict] = Field(default_factory=list)  # clarifying questions (max 2)
    model: str | None = None


# ── Info Summary ─────────────────────────────────────────


class MedInfoSummaryRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    med_name: str | None = None


class MedInfoSummaryResponse(BaseModel):
    name_candidates: list[str] = Field(default_factory=list)
    dosage_summary: str | None = None
    cautions_summary: str | None = None
    adverse_summary: str | None = None
    model: str | None = None
