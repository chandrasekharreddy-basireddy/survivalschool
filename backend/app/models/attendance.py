from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import Timestamped, UUIDPk

# ---- Attendance, tied to real timetable occurrences ----
#
# A TimetableEntry is a recurring weekly slot; an AttendanceSession is one
# concrete calendar occurrence of it (a specific date), opened by the
# instructor teaching that session. Students check in with a short-lived
# rotating code, or an instructor marks them directly — both paths land in
# AttendanceRecord.


class AttendanceSession(Base, UUIDPk, Timestamped):
    __tablename__ = "attendance_sessions"
    __table_args__ = (UniqueConstraint("timetable_entry_id", "session_date", name="uq_attendance_session_occurrence"),)

    timetable_entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("timetable_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    opened_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    check_in_code: Mapped[str] = mapped_column(String(10), nullable=False)
    code_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AttendanceRecord(Base, UUIDPk, Timestamped):
    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("session_id", "student_id", name="uq_attendance_record_student"),)

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="present", nullable=False)  # present|absent|excused
    method: Mapped[str] = mapped_column(String(20), default="code", nullable=False)  # code|manual|import
    checked_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    marked_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
