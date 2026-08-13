from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import Timestamped, UUIDPk


class PointsLedger(Base, UUIDPk, Timestamped):
    """Append-only ledger — the source of truth for a student's total points.

    Never mutate a row; always insert. Totals are SUM() over this table (or a
    materialized/cached rollup), which makes point awards auditable and makes
    client-submitted point values irrelevant (spec section 16: server-side only).
    """

    __tablename__ = "points"

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)  # lesson_complete|quiz_pass|exam_pass|streak|badge
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class Streak(Base, UUIDPk, Timestamped):
    __tablename__ = "streaks"
    __table_args__ = (UniqueConstraint("student_id", name="uq_streak_student"),)

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    current_streak_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    longest_streak_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_activity_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Badge(Base, UUIDPk, Timestamped):
    __tablename__ = "badges"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    icon: Mapped[str] = mapped_column(String(50), default="star", nullable=False)
    criteria_code: Mapped[str] = mapped_column(String(50), nullable=False)  # matches a server-side evaluator key


class Achievement(Base, UUIDPk, Timestamped):
    """A badge actually awarded to a student — server-evaluated only."""

    __tablename__ = "achievements"
    __table_args__ = (UniqueConstraint("student_id", "badge_id", name="uq_achievement_student_badge"),)

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    badge_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("badges.id", ondelete="CASCADE"), nullable=False)
    awarded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class LeaderboardSnapshot(Base, UUIDPk, Timestamped):
    """Periodic materialized snapshot so leaderboard reads don't hammer the points ledger."""

    __tablename__ = "leaderboards"

    scope: Mapped[str] = mapped_column(String(20), nullable=False)  # global|course
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    total_points: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[str] = mapped_column(String(20), default="all_time", nullable=False)  # all_time|weekly|monthly
