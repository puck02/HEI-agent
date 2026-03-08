"""
Health data Pydantic schemas — sync, daily advice, follow-up, insight.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Sync (leaf types first to avoid forward references) ──


class QuestionResponseSync(BaseModel):
    question_id: str
    step_index: int
    answer_type: str
    answer_value: str | None = None
    answer_label: str | None = None
    metadata_json: dict | None = None


class DailyAdviceSync(BaseModel):
    model: str | None = None
    advice_json: dict | None = None
    prompt_hash: str | None = None
    generated_at: int | None = None


class DailySummarySync(BaseModel):
    window_7d_json: dict | None = None
    window_30d_json: dict | None = None
    computed_at: int | None = None


class MedicationSync(BaseModel):
    android_id: int
    name: str
    aliases: str | None = None
    note: str | None = None
    info_summary: str | None = None


class MedicationCourseSync(BaseModel):
    med_android_id: int
    start_date: date
    end_date: date | None = None
    status: str = "active"
    frequency_text: str | None = None
    dose_text: str | None = None
    time_hints: str | None = None


class HealthEntrySync(BaseModel):
    android_id: int
    entry_date: date
    timezone_id: str | None = None
    created_at: int  # epoch millis
    question_responses: list[QuestionResponseSync] = []
    daily_advice: DailyAdviceSync | None = None
    daily_summary: DailySummarySync | None = None


class SyncUploadRequest(BaseModel):
    last_sync_timestamp: int = 0
    entries: list[HealthEntrySync] = []
    medications: list[MedicationSync] = []
    medication_courses: list[MedicationCourseSync] = []


class SyncResponse(BaseModel):
    message: str
    entries_synced: int = 0
    medications_synced: int = 0
    server_timestamp: int = 0


class SyncStatusResponse(BaseModel):
    last_sync_timestamp: int = 0
    total_entries: int = 0
    total_medications: int = 0
    server_cursor: int = 0
    capabilities: list[str] = Field(default_factory=list)
    last_push_ack: str | None = None


class SyncChange(BaseModel):
    entity: str
    op: str  # upsert | delete
    payload: dict[str, Any] = Field(default_factory=dict)


class SyncPushRequest(BaseModel):
    client_change_id: str
    base_server_version: int = 0
    changes: list[SyncChange] = Field(default_factory=list)


class SyncPushResult(BaseModel):
    entity: str
    op: str
    status: str  # applied | conflict | ignored | failed
    android_id: int | None = None
    server_id: int | None = None
    server_version: int | None = None
    conflict_reason: str | None = None


class SyncPushResponse(BaseModel):
    message: str
    accepted: int = 0
    applied: int = 0
    conflicts: int = 0
    server_timestamp: int = 0
    server_cursor: int = 0
    results: list[SyncPushResult] = Field(default_factory=list)


class SyncEntityEnvelope(BaseModel):
    entity: str
    record_id: int
    server_version: int
    updated_at: int
    payload: dict[str, Any] = Field(default_factory=dict)


class SyncTombstone(BaseModel):
    entity: str
    record_id: int
    deleted_at: int
    payload: dict[str, Any] = Field(default_factory=dict)


class SyncPullResponse(BaseModel):
    changes: list[SyncEntityEnvelope] = Field(default_factory=list)
    tombstones: list[SyncTombstone] = Field(default_factory=list)
    next_cursor: int = 0
    server_time: int = 0


# ── Daily Advice (Android-compatible) ────────────────────


class DailyAdviceRequest(BaseModel):
    """Input for daily advice generation — matches Android DailyAdviceCoordinator."""
    today_answers: dict[str, Any]  # all question_id → answer pairs
    summary_7d: dict | None = None
    active_meds_summary: list[str] | None = None
    today_med_changes: str | None = None
    adherence_hint: str | None = None


class DailyAdviceResponse(BaseModel):
    """Output — matches Android DailyAdvice JSON schema."""
    observations: list[str] = []
    actions: list[str] = []
    tomorrow_focus: list[str] = []
    red_flags: list[str] = []
    model: str | None = None


# ── Follow-Up Questions (Android-compatible) ─────────────


class FollowUpRequest(BaseModel):
    today_answers: dict[str, Any]
    summary_7d: dict | None = None
    triggered_symptoms: list[str] = []


class FollowUpQuestion(BaseModel):
    text: str
    type: str  # choice / slider
    options: list[str] | None = None
    min_value: int | None = None
    max_value: int | None = None


class FollowUpResponse(BaseModel):
    questions: list[FollowUpQuestion] = []
    model: str | None = None


# ── Weekly Insight (Android-compatible) ──────────────────


class WeeklyInsightRequest(BaseModel):
    week_start_date: date
    week_end_date: date
    summary_7d: dict
    summary_30d: dict | None = None
    active_meds_summary: list[str] | None = None


class WeeklyInsightResponse(BaseModel):
    schema_version: int = 1
    week_start_date: date
    week_end_date: date
    summary: str
    highlights: list[str] = []
    suggestions: list[str] = []
    cautions: list[str] = []
    confidence: str = "medium"  # low / medium / high
    model: str | None = None
