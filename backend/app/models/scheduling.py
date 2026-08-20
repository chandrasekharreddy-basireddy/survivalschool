from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import Timestamped, UUIDPk


class AIExamRegistrationWindow(Base, UUIDPk, Timestamped):
    """Global singleton describing when registration for the AI weekly exam
    is open. Gates *exam registration only* — account signup is open every
    day (see auth.py's register endpoint, which no longer checks this).

    This used to be named RegistrationWindow and (incorrectly, for this
    product) gated new-account signup itself. Renamed and repointed: the
    Thursday-only day-of-week logic that used to block creating an account
    now blocks joining the AI weekly exam cohort instead — see
    registration_service.py for the actual open/closed computation.

    `singleton` exists purely to enforce single-row-ness at the database
    level: it's always True and carries a unique constraint, so a second row
    physically cannot be inserted. Without it, get_or_create_window()'s
    SELECT-then-INSERT is a plain race — and it's reachable from an
    unauthenticated, unthrottled endpoint, so two concurrent first-hits
    after a fresh deploy could each insert their own "singleton" with
    nothing to detect the duplication afterwards.
    """
    __tablename__ = "ai_exam_registration_windows"
    __table_args__ = (UniqueConstraint("singleton", name="uq_ai_exam_registration_window_singleton"),)

    singleton: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    next_open_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    override_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
