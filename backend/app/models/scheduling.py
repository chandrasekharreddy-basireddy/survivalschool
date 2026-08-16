from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import Timestamped, UUIDPk


class RegistrationWindow(Base, UUIDPk, Timestamped):
    __tablename__ = "registration_windows"

    is_open: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    next_open_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    override_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ScheduledExamConfig(Base, UUIDPk, Timestamped):
    __tablename__ = "scheduled_exam_configs"
    __table_args__ = (
        UniqueConstraint("day_of_week", "time_slot", "course_id", name="uq_scheduled_exam_slot_course"),
    )

    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # Monday=0 ... Sunday=6
    time_slot: Mapped[str] = mapped_column(String(5), nullable=False)  # HH:MM in IST
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    auto_certificate_top_n: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(30), default="mixed", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_occurrence_key: Mapped[str | None] = mapped_column(String(32))
    title_prefix: Mapped[str] = mapped_column(String(120), default="Weekend AI Exam", nullable=False)
