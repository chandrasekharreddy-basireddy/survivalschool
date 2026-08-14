from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import Timestamped, UUIDPk


class DailyChallenge(Base, UUIDPk, Timestamped):
    """One real question from the existing question bank, selected once per
    calendar day (UTC) and shared by every student — the same "same puzzle
    for everyone today" mechanic real engagement products use. Created
    lazily on first request each day (see
    app/services/daily_challenge_service.py), not by a cron job — there's
    nothing to precompute, and lazy creation is race-safe via the unique
    constraint below plus a SAVEPOINT at the call site."""

    __tablename__ = "daily_challenges"
    __table_args__ = (UniqueConstraint("challenge_date", name="uq_daily_challenge_date"),)

    challenge_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )


class DailyChallengeAttempt(Base, UUIDPk, Timestamped):
    """One attempt per student per challenge — enforced by the unique
    constraint (a student cannot re-roll the same day's question for more
    points). Scored server-side against the real Question/QuestionOption
    answer key, exactly like quizzes/exams/practice."""

    __tablename__ = "daily_challenge_attempts"
    __table_args__ = (UniqueConstraint("student_id", "challenge_id", name="uq_daily_challenge_attempt"),)

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("daily_challenges.id", ondelete="CASCADE"), nullable=False, index=True
    )
    selected_option_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    text_answer: Mapped[str | None] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    points_awarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
