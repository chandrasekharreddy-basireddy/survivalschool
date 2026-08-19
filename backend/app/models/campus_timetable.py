from __future__ import annotations

import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import Timestamped, UUIDPk

# ---- Campus timetable: the university's own class schedule ----
#
# Deliberately separate from TimetableEntry (app/models/timetable.py), which
# models a recurring weekly slot for a course this platform actually teaches
# and enrolls students in. A university's full class schedule covers courses
# and sections this platform has no record of at all — forcing every row
# into a Course FK would either pollute the course catalog with rows that
# aren't real learning content, or reject most of a real spreadsheet
# outright. So this is its own read-mostly model, populated by upload or by
# polling a published spreadsheet, with no FK into the LMS's own courses.


class CampusTimetableSource(Base, UUIDPk, Timestamped):
    """Singleton config for how the campus timetable stays in sync — same
    singleton-column-plus-unique-constraint pattern as RegistrationWindow,
    since there is exactly one campus timetable feed per deployment."""

    __tablename__ = "campus_timetable_sources"
    __table_args__ = (UniqueConstraint("singleton", name="uq_campus_timetable_source_singleton"),)

    singleton: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="upload", nullable=False)  # upload|live_sync
    sheet_csv_url: Mapped[str | None] = mapped_column(String(2048))
    poll_interval_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_status: Mapped[str | None] = mapped_column(String(20))  # ok|error
    last_sync_error: Mapped[str | None] = mapped_column(String(500))
    last_sync_row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


class CampusTimetableEntry(Base, UUIDPk, Timestamped):
    """One concrete class occurrence on a real calendar date — mirrors the
    row shape of the y-bow/SaiU-Timetable reference sheet (school, year,
    section, lab group, course, day, date, start/end time, room, teacher,
    elective flag), not a recurring slot. A real campus schedule is full of
    one-off exceptions (moved rooms, cancelled single sessions) that a
    recurring model can't represent cleanly; per-date rows can.
    """

    __tablename__ = "campus_timetable_entries"
    __table_args__ = (
        UniqueConstraint("row_key", name="uq_campus_timetable_entry_row_key"),
        Index("ix_campus_timetable_section_date", "section", "class_date"),
    )

    row_key: Mapped[str] = mapped_column(String(64), nullable=False)  # stable identity hash — see service
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # content hash — used to detect real changes
    school: Mapped[str | None] = mapped_column(String(120))
    # The student's year *of study* within their program (e.g. "1"–"4"), not
    # a calendar/academic year like "2026" — matches the source spreadsheet's
    # own "year" column, per the y-bow/SaiU-Timetable reference this format
    # is modeled on (its own record shape uses `"year": 3` this way).
    year_of_study: Mapped[str | None] = mapped_column(String(20))
    section: Mapped[str] = mapped_column(String(60), nullable=False)
    lab_group: Mapped[str | None] = mapped_column(String(60))
    course_name: Mapped[str] = mapped_column(String(200), nullable=False)
    course_code: Mapped[str | None] = mapped_column(String(40))
    class_date: Mapped[date] = mapped_column(Date, nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    room: Mapped[str | None] = mapped_column(String(100))
    teacher_name: Mapped[str | None] = mapped_column(String(150))
    is_elective: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="upload", nullable=False)  # upload|live_sync
