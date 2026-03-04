"""
Memory ORM model — long-term memory storage with embedding support.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MemoryEntry(Base):
    """Long-term memory entries with vector embeddings for semantic retrieval."""

    __tablename__ = "memory_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    memory_type: Mapped[str] = mapped_column(
        String(50), index=True
    )  # health_pattern / preference / medical_history / conversation_summary
    content: Mapped[str] = mapped_column(Text)
    importance_score: Mapped[float] = mapped_column(Float, default=1.0)
    # Store embedding as float array — use pgvector extension for similarity search
    embedding: Mapped[list[float] | None] = mapped_column(
        ARRAY(Float), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    user = relationship("User", back_populates="memories")

    def __repr__(self) -> str:
        return f"<MemoryEntry(id={self.id}, type={self.memory_type}, score={self.importance_score:.2f})>"
