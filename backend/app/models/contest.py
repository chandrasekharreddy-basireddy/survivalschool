from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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
        Index("ix_contests_status_ends_at", "status", "ends_at"),
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    contest_type: Mapped[str] = mapped_column(String(20), nullable=False)
    occurrence_key: Mapped[str | None] = mapped_column(String(60))
    is_auto_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=1800, nullable=False)
    question_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    top_n_awarded: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="scheduled", nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContestAttempt(Base, UUIDPk, Timestamped):
    __tablename__ = "contest_attempts"
    __table_args__ = (
        UniqueConstraint("contest_id", "student_id", name="uq_contest_attempt_student"),
        Index("ix_contest_attempts_contest_status", "contest_id", "status"),
        # Same database-level score/status guards the exam_attempts and
        # quiz_attempts tables already have — contest_attempts was left out of
        # the migration that added them despite having identical columns.
        CheckConstraint("score_percent IS NULL OR (score_percent >= 0 AND score_percent <= 100)", name="score_percent_range"),
        CheckConstraint("points_earned IS NULL OR points_earned >= 0", name="points_earned_non_negative"),
        CheckConstraint("points_possible IS NULL OR points_possible >= 0", name="points_possible_non_negative"),
        CheckConstraint("points_earned IS NULL OR points_possible IS NULL OR points_earned <= points_possible", name="points_earned_within_possible"),
        CheckConstraint("status IN ('in_progress', 'submitted', 'abandoned')", name="status_valid"),
    )

    contest_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contests.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    question_order: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    server_deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_taken_seconds: Mapped[int | None] = mapped_column(Integer)
    score_percent: Mapped[int | None] = mapped_column(Integer)
    points_earned: Mapped[int | None] = mapped_column(Integer)
    points_possible: Mapped[int | None] = mapped_column(Integer)
    rank: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="in_progress", nullable=False)


class ContestAnswer(Base, UUIDPk, Timestamped):
    __tablename__ = "contest_answers"

    attempt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contest_attempts.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False)
    selected_option_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    text_answer: Mapped[str | None] = mapped_column(Text)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    points_awarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ContestCertificate(Base, UUIDPk, Timestamped):
    """Contest award certificate with the same lifecycle guarantees as course certificates.

    Contest certificates remain separate because they are not tied to a course,
    but now support verification, QR/PDF presentation, expiry, and audited
    revocation just like course certificates.
    """
    __tablename__ = "contest_certificates"
    __table_args__ = (UniqueConstraint("contest_id", "student_id", name="uq_contest_certificate_student"),)

    certificate_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    # SET NULL, not CASCADE — deleting a contest must not destroy the
    # certificates already awarded for it. contest_title/rank/score_percent
    # below are snapshotted at issuance, so the credential stays fully
    # renderable and verifiable without the contest row.
    contest_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("contests.id", ondelete="SET NULL"), nullable=True)
    # Indexed: "my contest certificates" filters on student_id alone, which the
    # (contest_id, student_id) unique constraint can't serve as its leading column.
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    contest_title: Mapped[str] = mapped_column(String(200), nullable=False)
    score_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
