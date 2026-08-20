"""The shared question bank. Used by contests (AI weekly exam), elimination
battles, and ai_practice sessions — never course-scoped (the old
course-linked Quiz/Exam system that used to live in this file was removed
along with courses; contest_service.py/elimination_service.py now generate
Question rows tagged by subject/topic instead of drawing from a
course-linked bank).
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import Timestamped, UUIDPk


class Question(Base, UUIDPk, Timestamped):
    __tablename__ = "questions"
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="SET NULL"), index=True)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="SET NULL"), index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    # "single" (MCQ, exactly one correct option) | "multiple" (MSQ, one or
    # more correct options) | "true_false" | "short_answer".
    question_type: Mapped[str] = mapped_column(String(30), nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    short_answer_key: Mapped[str | None] = mapped_column(String(500))
    # AI-generated questions are never blindly trusted into a live exam —
    # question_validation_service checks structure/answer-count/duplicates
    # before is_validated flips true. Only validated questions are eligible
    # for contest/elimination-battle question selection.
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_validated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    options: Mapped[list[QuestionOption]] = relationship(cascade="all, delete-orphan", order_by="QuestionOption.order_index")


class QuestionOption(Base, UUIDPk, Timestamped):
    __tablename__ = "question_options"
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True)
    text: Mapped[str] = mapped_column(String(1000), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
