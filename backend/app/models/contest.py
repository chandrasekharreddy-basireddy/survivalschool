from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import Timestamped, UUIDPk

# ---- Platform-wide competitive contests ----
#
# A Contest snapshots a fixed set of real, already-authored Question rows
# (drawn from published courses' question banks — never AI-generated, never
# invented) at creation time, the same way Quiz/Exam already snapshot
# question_ids. Auto-generated contests (weekly Sat/Sun AM+PM IST, monthly)
# are created idempotently by the worker via `occurrence_key`; admin-created
# ad hoc contests leave it null. See app/services/contest_service.py.


class Contest(Base, UUIDPk, Timestamped):
    __tablename__ = "contests"
    __table_args__ = (
        UniqueConstraint("occurrence_key", name="uq_contest_occurrence_key"),
        # The scheduler's finalize job scans for exactly this: contests whose
        # window has closed but haven't been ranked/awarded yet.
        Index("ix_contests_status_ends_at", "status", "ends_at"),
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    contest_type: Mapped[str] = mapped_column(String(20), nullable=False)  # weekly_morning|weekly_evening|monthly|custom
    # Idempotency key for auto-generated occurrences, e.g. "weekly-sat-am-2026-08-15".
    # Null for admin-created custom contests. The unique constraint above is what
    # actually prevents a double-create if the scheduler job overlaps itself.
    occurrence_key: Mapped[str | None] = mapped_column(String(60))
    is_auto_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Per-student attempt duration once they start, capped by ends_at — mirrors
    # Exam.time_limit_seconds/server_deadline_at, see contest_service.py.
    duration_seconds: Mapped[int] = mapped_column(Integer, default=1800, nullable=False)

    question_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    top_n_awarded: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="scheduled", nullable=False)  # scheduled|open|closed
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContestAttempt(Base, UUIDPk, Timestamped):
    __tablename__ = "contest_attempts"
    __table_args__ = (
        UniqueConstraint("contest_id", "student_id", name="uq_contest_attempt_student"),
        Index("ix_contest_attempts_contest_status", "contest_id", "status"),
    )

    contest_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contests.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    question_order: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    server_deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_taken_seconds: Mapped[int | None] = mapped_column(Integer)  # tiebreak: faster finish ranks higher
    score_percent: Mapped[int | None] = mapped_column(Integer)
    points_earned: Mapped[int | None] = mapped_column(Integer)
    points_possible: Mapped[int | None] = mapped_column(Integer)
    rank: Mapped[int | None] = mapped_column(Integer)  # set by contest_service.finalize_contest()
    status: Mapped[str] = mapped_column(String(20), default="in_progress", nullable=False)  # in_progress|submitted


class ContestAnswer(Base, UUIDPk, Timestamped):
    __tablename__ = "contest_answers"

    attempt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contest_attempts.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False)
    selected_option_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    text_answer: Mapped[str | None] = mapped_column(Text)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    points_awarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ContestCertificate(Base, UUIDPk, Timestamped):
    """Deliberately a separate table from `certificates` rather than
    reworking that model's NOT NULL course_id — a contest win isn't tied to
    a course, and the course-certificate issuance/verification flow is
    heavily tested; this keeps that flow untouched."""
    __tablename__ = "contest_certificates"
    __table_args__ = (UniqueConstraint("contest_id", "student_id", name="uq_contest_certificate_student"),)

    certificate_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    contest_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contests.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    contest_title: Mapped[str] = mapped_column(String(200), nullable=False)  # snapshotted, same reasoning as Certificate
    score_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
