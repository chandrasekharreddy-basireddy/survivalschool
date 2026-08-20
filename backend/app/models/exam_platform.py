"""Core taxonomy for the competitive exam platform: University -> Subject ->
Topic. Replaces the old Course/CourseSection/Lesson tree — there is no
enrollment or teaching content here, only the classification that Question
rows, Contests (AI weekly exams), and elimination battles are tagged by.

Single-university deployment for now (see University.singleton, mirroring
the existing RegistrationWindow singleton pattern in scheduling.py), but
modeled as a real table + FK rather than a hardcoded string so a second
university can be added later without a schema rewrite.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import Timestamped, UUIDPk


class University(Base, UUIDPk, Timestamped):
    __tablename__ = "universities"
    __table_args__ = (UniqueConstraint("singleton", name="uq_university_singleton"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Same one-row-only trick as RegistrationWindow: a unique constraint on a
    # column that only ever holds `true` makes a second row physically
    # impossible, without a bespoke "is there already a row" race to protect
    # in application code.
    singleton: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Subject(Base, UUIDPk, Timestamped):
    __tablename__ = "subjects"
    __table_args__ = (UniqueConstraint("university_id", "slug", name="uq_subject_university_slug"),)

    university_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("universities.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Topic(Base, UUIDPk, Timestamped):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("subject_id", "slug", name="uq_topic_subject_slug"),)

    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TopicDifficultyEvaluation(Base, UUIDPk, Timestamped):
    """A real, inspectable difficulty score for a topic — not an opaque "AI
    said 74%" number. Computed by difficulty_service.evaluate_topic_difficulty
    from a documented formula (question complexity metadata + historical
    accuracy on that topic, see the service's module docstring for the exact
    weights), and persisted here with the formula_version and a human-
    readable `reason` so every score is reproducible and auditable rather
    than a black box a student or admin has to just trust.

    One row per topic per evaluation run — history is kept (not
    overwritten) so a topic's difficulty trend is visible and a stale
    evaluation can be told apart from the current one via `is_current`.
    """
    __tablename__ = "topic_difficulty_evaluations"

    topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)
    difficulty_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    formula_version: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
