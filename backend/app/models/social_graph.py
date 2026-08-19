from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import Timestamped, UUIDPk

# ---- Follow requests (Instagram-style) ----
#
# Sending a follow request never grants anything by itself — it only ever
# unlocks something once the *target* accepts it, mirroring the real
# Instagram flow this was asked to match. Two things key off an accepted
# request: it lets each side start messaging the other (see
# chat.py::start_direct_message, which checks has_accepted_connection()
# before ever creating or reusing a direct ChatRoom), and it drives the
# "follow request received / accepted" notifications. Declining or
# cancelling a request is reversible — re-requesting after a decline just
# resets the same row back to pending rather than erroring, matching how a
# real social app lets you try again.


class FollowRequest(Base, UUIDPk, Timestamped):
    __tablename__ = "follow_requests"
    __table_args__ = (
        UniqueConstraint("requester_id", "target_id", name="uq_follow_request_pair"),
        CheckConstraint("requester_id != target_id", name="ck_follow_request_not_self"),
        CheckConstraint("status IN ('pending', 'accepted', 'declined')", name="ck_follow_request_status_valid"),
    )

    requester_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
