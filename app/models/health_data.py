"""
Health data ORM models — mirrors HElDairy Android Room entities.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class HealthEntry(Base):
    """Mirrors DailyEntryEntity — one row per day of health reporting."""

    __tablename__ = "health_entries"
    __table_args__ = (
        UniqueConstraint("user_id", "entry_date", name="uq_user_entry_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    timezone_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Android-side Room ID for mapping back
    android_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    user = relationship("User", back_populates="health_entries")
    question_responses = relationship(
        "QuestionResponse", back_populates="health_entry", cascade="all, delete-orphan"
    )
    daily_advice = relationship(
        "DailyAdvice", back_populates="health_entry", uselist=False, cascade="all, delete-orphan"
    )
    daily_summary = relationship(
        "DailySummary", back_populates="health_entry", uselist=False, cascade="all, delete-orphan"
    )


class QuestionResponse(Base):
    """Mirrors QuestionResponseEntity — individual question answers."""

    __tablename__ = "question_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("health_entries.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(String(100))
    step_index: Mapped[int] = mapped_column(Integer)
    answer_type: Mapped[str] = mapped_column(String(50))  # choice / slider / text
    answer_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    health_entry = relationship("HealthEntry", back_populates="question_responses")


class DailyAdvice(Base):
    """Mirrors DailyAdviceEntity — cached AI advice per day."""

    __tablename__ = "daily_advice"
    __table_args__ = (
        UniqueConstraint("entry_id", name="uq_daily_advice_entry"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("health_entries.id", ondelete="CASCADE"), index=True
    )
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    advice_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    health_entry = relationship("HealthEntry", back_populates="daily_advice")


class DailySummary(Base):
    """Mirrors DailySummaryEntity — rolling 7/30-day stat snapshots."""

    __tablename__ = "daily_summaries"
    __table_args__ = (
        UniqueConstraint("entry_id", name="uq_daily_summary_entry"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("health_entries.id", ondelete="CASCADE"), index=True
    )
    window_7d_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    window_30d_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    health_entry = relationship("HealthEntry", back_populates="daily_summary")


class InsightReport(Base):
    """Mirrors InsightReportEntity — weekly AI insight cache."""

    __tablename__ = "insight_reports"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start_date", name="uq_user_week_insight"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    week_start_date: Mapped[date] = mapped_column(Date)
    week_end_date: Mapped[date] = mapped_column(Date)
    ai_result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/success/failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class AdviceTracking(Base):
    """Mirrors AdviceTrackingEntity — user feedback on AI advice."""

    __tablename__ = "advice_tracking"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("health_entries.id", ondelete="CASCADE"), index=True
    )
    advice_text: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_field: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_feedback: Mapped[str | None] = mapped_column(String(50), nullable=True)
    effectiveness_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
