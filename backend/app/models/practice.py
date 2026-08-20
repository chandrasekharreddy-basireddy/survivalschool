from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import Timestamped, UUIDPk


class QuestionBookmark(Base, UUIDPk, Timestamped):
    __tablename__ = "question_bookmarks"
    __table_args__ = (UniqueConstraint("student_id", "question_id", name="uq_bookmark_student_question"),)

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    note: Mapped[str | None] = mapped_column(String(500))


class PracticeSession(Base, UUIDPk, Timestamped):
    """Untimed, low-stakes practice — deliberately separate from
    QuizAttempt/ExamAttempt. Practice sessions are graded server-side with
    the same real answer keys, but never award gamification points, never
    count toward certificate eligibility, and reveal correct answers
    immediately on submit (quizzes/exams never do that before their own
    review flow) — that's the point of a practice/review mode, not a bug."""

    __tablename__ = "practice_sessions"

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # bookmarks|mistakes
    question_order: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score_percent: Mapped[int | None] = mapped_column(Integer)
    points_earned: Mapped[int | None] = mapped_column(Integer)
    points_possible: Mapped[int | None] = mapped_column(Integer)


class PracticeAnswer(Base, UUIDPk, Timestamped):
    __tablename__ = "practice_answers"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("practice_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False)
    selected_option_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    text_answer: Mapped[str | None] = mapped_column(Text)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    points_awarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
