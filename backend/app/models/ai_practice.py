from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import Timestamped, UUIDPk

# ---- AI-generated practice questions ----
#
# Deliberately a completely separate table set from `questions` (the real,
# instructor-authored bank backing quizzes/exams/contests/certificates). A
# student can generate these for their own practice by naming a subject and
# a count; they are never inserted into `questions`, never eligible for a
# quiz/exam/contest, and completing a session never awards gamification
# points or affects a certificate — matching the practice-mode pattern
# already used for bookmarks/mistakes practice, and per explicit product
# direction: AI-generated content must never merge with the vetted bank.


class AIMockSession(Base, UUIDPk, Timestamped):
    __tablename__ = "ai_mock_sessions"

    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(150), nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)  # mock|sarvam — which AIProvider generated this
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score_percent: Mapped[int | None] = mapped_column(Integer)

    questions: Mapped[list[AIGeneratedQuestion]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="AIGeneratedQuestion.order_index"
    )


class AIGeneratedQuestion(Base, UUIDPk, Timestamped):
    __tablename__ = "ai_generated_questions"

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_mock_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    session: Mapped[AIMockSession] = relationship(back_populates="questions")
    options: Mapped[list[AIGeneratedQuestionOption]] = relationship(cascade="all, delete-orphan", order_by="AIGeneratedQuestionOption.order_index")


class AIGeneratedQuestionOption(Base, UUIDPk, Timestamped):
    __tablename__ = "ai_generated_question_options"

    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_generated_questions.id", ondelete="CASCADE"), nullable=False, index=True)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AIMockAnswer(Base, UUIDPk, Timestamped):
    __tablename__ = "ai_mock_answers"

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_mock_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_generated_questions.id", ondelete="CASCADE"), nullable=False)
    selected_option_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
