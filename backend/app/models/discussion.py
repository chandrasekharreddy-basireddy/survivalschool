from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import Timestamped, UUIDPk


class DiscussionThread(Base, UUIDPk, Timestamped):
    __tablename__ = "discussion_threads"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True, index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Denormalized for cheap sort-by-popularity — kept in sync inside the
    # upvote endpoint's own transaction, never trusted from a client.
    upvote_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class DiscussionReply(Base, UUIDPk, Timestamped):
    __tablename__ = "discussion_replies"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discussion_threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Set server-side (never client-supplied) when the replying user is the
    # course's instructor — lets the frontend badge an authoritative answer.
    is_instructor_answer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class DiscussionVote(Base, UUIDPk, Timestamped):
    __tablename__ = "discussion_votes"
    __table_args__ = (UniqueConstraint("thread_id", "user_id", name="uq_discussion_vote_thread_user"),)

    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discussion_threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
