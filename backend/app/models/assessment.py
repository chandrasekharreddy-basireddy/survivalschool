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
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import Timestamped, UUIDPk


class Question(Base, UUIDPk, Timestamped):
    __tablename__ = "questions"
    course_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"))
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String(30), nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    short_answer_key: Mapped[str | None] = mapped_column(String(500))
    options: Mapped[list[QuestionOption]] = relationship(cascade="all, delete-orphan", order_by="QuestionOption.order_index")


class QuestionOption(Base, UUIDPk, Timestamped):
    __tablename__ = "question_options"
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True)
    text: Mapped[str] = mapped_column(String(1000), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Quiz(Base, UUIDPk, Timestamped):
    __tablename__ = "quizzes"
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    time_limit_seconds: Mapped[int | None] = mapped_column(Integer)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    randomize_questions: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pass_score_percent: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    question_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class QuizAttempt(Base, UUIDPk, Timestamped):
    __tablename__ = "quiz_attempts"
    __table_args__ = (
        Index("ix_quiz_attempts_student_quiz_status", "student_id", "quiz_id", "status"),
        # The database is the last line of defence for scores: a service-layer
        # bug must not be able to persist 140%%, a negative score, or more points
        # earned than were available. (Kept as Integer rather than Numeric(5,2)
        # — percentages are whole numbers throughout the grading code and the
        # schemas/frontend; the range checks are what actually protect the data.)
        CheckConstraint("score_percent IS NULL OR (score_percent >= 0 AND score_percent <= 100)", name="score_percent_range"),
        CheckConstraint("points_earned IS NULL OR points_earned >= 0", name="points_earned_non_negative"),
        CheckConstraint("points_possible IS NULL OR points_possible >= 0", name="points_possible_non_negative"),
        CheckConstraint("points_earned IS NULL OR points_possible IS NULL OR points_earned <= points_possible", name="points_earned_within_possible"),
        CheckConstraint("status IN ('in_progress', 'submitted', 'abandoned')", name="status_valid"),
    )
    quiz_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    question_order: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score_percent: Mapped[int | None] = mapped_column(Integer)
    points_earned: Mapped[int | None] = mapped_column(Integer)
    points_possible: Mapped[int | None] = mapped_column(Integer)
    passed: Mapped[bool | None] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(20), default="in_progress", nullable=False)


class QuizAnswer(Base, UUIDPk, Timestamped):
    __tablename__ = "quiz_answers"
    attempt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("quiz_attempts.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False, index=True)
    selected_option_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    text_answer: Mapped[str | None] = mapped_column(Text)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    points_awarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Exam(Base, UUIDPk, Timestamped):
    __tablename__ = "exams"
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    time_limit_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    max_attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    pass_score_percent: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    available_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    question_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    fullscreen_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    integrity_monitoring_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_integrity_violations: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    is_ai_scheduled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_certificate_top_n: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ExamAttempt(Base, UUIDPk, Timestamped):
    __tablename__ = "exam_attempts"
    __table_args__ = (
        Index("ix_exam_attempts_student_exam_status", "student_id", "exam_id", "status"),
        # The database is the last line of defence for scores: a service-layer
        # bug must not be able to persist 140%%, a negative score, or more points
        # earned than were available. (Kept as Integer rather than Numeric(5,2)
        # — percentages are whole numbers throughout the grading code and the
        # schemas/frontend; the range checks are what actually protect the data.)
        CheckConstraint("score_percent IS NULL OR (score_percent >= 0 AND score_percent <= 100)", name="score_percent_range"),
        CheckConstraint("points_earned IS NULL OR points_earned >= 0", name="points_earned_non_negative"),
        CheckConstraint("points_possible IS NULL OR points_possible >= 0", name="points_possible_non_negative"),
        CheckConstraint("points_earned IS NULL OR points_possible IS NULL OR points_earned <= points_possible", name="points_earned_within_possible"),
        CheckConstraint("status IN ('in_progress', 'submitted', 'abandoned')", name="status_valid"),
    )
    exam_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    question_order: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    server_deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    autosaved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score_percent: Mapped[int | None] = mapped_column(Integer)
    points_earned: Mapped[int | None] = mapped_column(Integer)
    points_possible: Mapped[int | None] = mapped_column(Integer)
    passed: Mapped[bool | None] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(20), default="in_progress", nullable=False)
    # Unique + indexed: this is the exam-submit idempotency key. Without the
    # unique index two concurrent submits carrying the same token both pass the
    # "already seen?" SELECT and both grade the attempt, which is precisely what
    # the token exists to prevent. NULLs stay distinct in Postgres, so attempts
    # submitted without a token are unaffected. The index also turns the lookup
    # from a full scan of exam_attempts into a single probe.
    submission_client_token: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    flagged_events: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    allowed_ip: Mapped[str | None] = mapped_column(String(64))
    violation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ExamAnswer(Base, UUIDPk, Timestamped):
    __tablename__ = "exam_answers"
    attempt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("exam_attempts.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False, index=True)
    selected_option_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    text_answer: Mapped[str | None] = mapped_column(Text)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    points_awarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    autosaved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
