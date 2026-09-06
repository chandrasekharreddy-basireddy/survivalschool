"""Student-hosted elimination battles: one question at a time, a strict
15-second server-authoritative deadline per question, wrong/no answer
eliminates you immediately, last survivor wins. Independent of the AI
weekly exam (Contest) — a student creates and invites specific friends by
user id, not a scheduled platform-wide event.

Every timing decision here is server-side and durable (a Postgres row, not
in-process memory or a frontend setTimeout): EliminationRound.deadline_at
is written when the round is released and is what
elimination_service.submit_answer() and the expiry sweep both check. A
gunicorn worker restarting, or a participant's browser losing its
connection, cannot change what the deadline was — see
services/elimination_service.py for the full state machine and the
Redis-lock-guarded expiry sweep that enforces "no answer = eliminated"
even for a participant who never sends another request.
"""
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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import Timestamped, UUIDPk

QUESTION_DEADLINE_SECONDS = 15


class EliminationBattle(Base, UUIDPk, Timestamped):
    __tablename__ = "elimination_battles"
    __table_args__ = (
        CheckConstraint(
            "status IN ('lobby', 'active', 'completed', 'cancelled')", name="ck_elimination_battle_status"
        ),
        UniqueConstraint("join_code", name="uq_elimination_battle_join_code"),
    )

    host_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # Free Fire-style room code: anyone holding it can join the lobby
    # directly (see elimination_service.join_battle_by_code), deliberately
    # bypassing the connections-only restriction on invite_to_battle — the
    # whole point of a shareable code is reaching people who aren't yet
    # connections in-app.
    join_code: Mapped[str] = mapped_column(String(8), nullable=False)
    topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="lobby", nullable=False)
    current_round_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    winner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Optional: the host can schedule when the battle should auto-start
    # instead of clicking Start themselves — see elimination_service.py's
    # sweep loop, which activates any lobby battle whose scheduled_start_at
    # has passed and has at least 2 participants. Null means host-started
    # only, the original behavior.
    scheduled_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Every battle gets one of these at creation (see
    # elimination_service.create_battle) — reuses the existing chat_rooms/
    # chat_members/chat_messages tables and /ws/chat/{room_id} socket
    # rather than building a separate persistence/websocket path for
    # battle chat. Nullable only because it's set right after the row is
    # first inserted (needs the battle's own id to exist as created_by
    # context isn't required, but the FK ordering is simpler this way);
    # every battle created through create_battle always has one.
    chat_room_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_rooms.id", ondelete="SET NULL"))


class EliminationInvitation(Base, UUIDPk, Timestamped):
    __tablename__ = "elimination_invitations"
    __table_args__ = (
        UniqueConstraint("battle_id", "invitee_id", name="uq_elimination_invite_battle_invitee"),
        CheckConstraint("status IN ('pending', 'accepted', 'declined', 'expired')", name="ck_elimination_invite_status"),
        CheckConstraint("inviter_id != invitee_id", name="ck_elimination_invite_not_self"),
    )

    battle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("elimination_battles.id", ondelete="CASCADE"), nullable=False, index=True)
    inviter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    invitee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EliminationParticipant(Base, UUIDPk, Timestamped):
    __tablename__ = "elimination_participants"
    __table_args__ = (
        UniqueConstraint("battle_id", "user_id", name="uq_elimination_participant_battle_user"),
        CheckConstraint(
            "status IN ('ready', 'active', 'eliminated', 'winner')", name="ck_elimination_participant_status"
        ),
    )

    battle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("elimination_battles.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="ready", nullable=False)
    eliminated_at_round: Mapped[int | None] = mapped_column(Integer)
    eliminated_reason: Mapped[str | None] = mapped_column(String(30))  # wrong_answer | timeout


class EliminationRound(Base, UUIDPk, Timestamped):
    """One row per (battle, round_number). Created the instant a round is
    released — deadline_at is computed and written at that moment, so it is
    fixed the moment the question exists, before any client has even
    received it over the websocket. Nothing about this row is derived from
    a client request."""
    __tablename__ = "elimination_rounds"
    __table_args__ = (
        UniqueConstraint("battle_id", "round_number", name="uq_elimination_round_battle_number"),
        # The expiry sweep (elimination_service._sweep_once) runs this exact
        # WHERE clause every SWEEP_INTERVAL_SECONDS (2s), unconditionally,
        # for the process's lifetime. A partial index — only unresolved rows
        # are ever matched, and once resolved a row never becomes unresolved
        # again — keeps that scan cheap regardless of how many total rounds
        # have accumulated across every battle ever played.
        Index("ix_elimination_rounds_sweep", "deadline_at", postgresql_where=text("resolved_at IS NULL")),
    )

    battle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("elimination_battles.id", ondelete="CASCADE"), nullable=False, index=True)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False)
    released_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EliminationAnswer(Base, UUIDPk, Timestamped):
    __tablename__ = "elimination_answers"
    __table_args__ = (
        # One answer per participant per round — the idempotency guard that
        # makes a retried/duplicated submit request a safe no-op instead of
        # a second grading pass.
        UniqueConstraint("round_id", "participant_id", name="uq_elimination_answer_round_participant"),
    )

    round_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("elimination_rounds.id", ondelete="CASCADE"), nullable=False, index=True)
    participant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("elimination_participants.id", ondelete="CASCADE"), nullable=False, index=True)
    selected_option_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
