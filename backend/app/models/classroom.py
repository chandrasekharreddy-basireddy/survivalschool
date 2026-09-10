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


class Classroom(Base, UUIDPk, Timestamped):
    __tablename__ = "classrooms"
    __table_args__ = (
        UniqueConstraint("join_code", name="uq_classrooms_join_code"),
        Index("ix_classrooms_lecturer_id", "lecturer_id"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="SET NULL")
    )
    section: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    join_code: Mapped[str] = mapped_column(String(8), nullable=False)
    lecturer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ClassroomMember(Base, UUIDPk, Timestamped):
    __tablename__ = "classroom_members"
    __table_args__ = (
        UniqueConstraint("classroom_id", "student_id", name="uq_classroom_member"),
        Index("ix_classroom_members_student_id", "student_id"),
    )

    classroom_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClassroomExam(Base, UUIDPk, Timestamped):
    __tablename__ = "classroom_exams"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'scheduled', 'open', 'closed')",
            name="classroom_exam_status_valid",
        ),
        Index("ix_classroom_exams_classroom_id", "classroom_id"),
        Index("ix_classroom_exams_status", "status"),
    )

    classroom_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    question_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=1800, nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    fullscreen_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    integrity_monitoring_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_integrity_violations: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    max_warnings_before_terminate: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    face_proctoring_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ClassroomExamAttempt(Base, UUIDPk, Timestamped):
    __tablename__ = "classroom_exam_attempts"
    __table_args__ = (
        UniqueConstraint("exam_id", "student_id", name="uq_classroom_exam_attempt_student"),
        CheckConstraint(
            "status IN ('in_progress', 'submitted', 'terminated')",
            name="classroom_exam_attempt_status_valid",
        ),
        Index("ix_classroom_exam_attempts_exam_id", "exam_id"),
    )

    exam_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("classroom_exams.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_order: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    server_deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_taken_seconds: Mapped[int | None] = mapped_column(Integer)
    score_percent: Mapped[int | None] = mapped_column(Integer)
    points_earned: Mapped[int | None] = mapped_column(Integer)
    points_possible: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="in_progress", nullable=False)
    device_fingerprint: Mapped[str | None] = mapped_column(String(256))
    violation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    flagged_events: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)


class ClassroomExamAnswer(Base, UUIDPk, Timestamped):
    __tablename__ = "classroom_exam_answers"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("classroom_exam_attempts.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False
    )
    selected_option_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    points_awarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
