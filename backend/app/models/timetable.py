from __future__ import annotations

import uuid
from datetime import date, time

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import Timestamped, UUIDPk


class TimetableEntry(Base, UUIDPk, Timestamped):
    """A recurring weekly class slot for a course, scoped to an academic term.

    There is deliberately no separate per-student schedule table — a
    student's personal timetable (GET /timetable/me) is derived at query
    time by joining their active Enrollment rows against these entries, so a
    schedule change an instructor makes is immediately reflected for every
    enrolled student without a backfill job.

    day_of_week follows Python's date.weekday() convention: 0=Monday .. 6=Sunday.
    """

    __tablename__ = "timetable_entries"
    __table_args__ = (
        # Conflict detection (services/timetable_service.py) filters by
        # exactly this triple on every create/update — same reasoning as the
        # composite indexes added on quiz_attempts/exam_attempts.
        Index("ix_timetable_term_day", "term", "day_of_week"),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instructor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    term: Mapped[str] = mapped_column(String(40), nullable=False)  # e.g. "2026-Fall"
    term_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    term_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    room: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    session_type: Mapped[str] = mapped_column(String(20), default="lecture", nullable=False)  # lecture|lab|seminar|exam
