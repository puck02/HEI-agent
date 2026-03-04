"""
Medication ORM models — mirrors HElDairy Android Room medication entities.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Medication(Base):
    """Mirrors MedEntity — medication library."""

    __tablename__ = "medications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    aliases: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    info_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    android_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user = relationship("User", back_populates="medications")
    courses = relationship(
        "MedicationCourse", back_populates="medication", cascade="all, delete-orphan"
    )
    reminders = relationship(
        "MedicationReminder", back_populates="medication", cascade="all, delete-orphan"
    )


class MedicationCourse(Base):
    """Mirrors MedCourseEntity — medication treatment courses."""

    __tablename__ = "medication_courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    med_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("medications.id", ondelete="CASCADE"), index=True
    )
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/paused/ended
    frequency_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dose_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    time_hints: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    medication = relationship("Medication", back_populates="courses")


class MedicationEvent(Base):
    """Mirrors MedEventEntity — NLP event log."""

    __tablename__ = "medication_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    raw_text: Mapped[str] = mapped_column(Text)
    detected_med_names_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    proposed_actions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confirmed_actions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    apply_result: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class MedicationReminder(Base):
    """Mirrors MedicationReminderEntity — scheduled medication reminders."""

    __tablename__ = "medication_reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    med_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("medications.id", ondelete="CASCADE"), index=True
    )
    hour: Mapped[int] = mapped_column(Integer)
    minute: Mapped[int] = mapped_column(Integer)
    repeat_type: Mapped[str] = mapped_column(String(20), default="daily")
    week_days: Mapped[str | None] = mapped_column(String(50), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    medication = relationship("Medication", back_populates="reminders")
