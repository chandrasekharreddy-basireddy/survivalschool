from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BattleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    subject_name: str = Field(min_length=1, max_length=150)
    topic_name: str = Field(min_length=1, max_length=150)
    # Optional: schedule an auto-start instead of the host clicking Start —
    # see elimination_service.py's sweep loop.
    scheduled_start_at: datetime | None = None


class BattleOut(BaseModel):
    id: uuid.UUID
    host_id: uuid.UUID
    title: str
    topic_id: uuid.UUID
    status: str
    current_round_number: int
    winner_id: uuid.UUID | None
    started_at: datetime | None
    ended_at: datetime | None
    scheduled_start_at: datetime | None
    join_code: str
    model_config = {"from_attributes": True}


class JoinByCodeIn(BaseModel):
    code: str = Field(min_length=4, max_length=8)


class InviteCreate(BaseModel):
    invitee_id: uuid.UUID


class InvitationOut(BaseModel):
    id: uuid.UUID
    battle_id: uuid.UUID
    battle_title: str
    inviter_id: uuid.UUID
    inviter_name: str
    inviter_handle: str | None
    invitee_id: uuid.UUID
    status: str
    created_at: datetime


class ParticipantOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    public_handle: str | None
    status: str
    eliminated_at_round: int | None
    eliminated_reason: str | None


class SubmitAnswerIn(BaseModel):
    selected_option_ids: list[uuid.UUID] = Field(default=[], max_length=20)


class SubmitAnswerOut(BaseModel):
    is_correct: bool
    eliminated: bool


class RoundOptionOut(BaseModel):
    id: uuid.UUID
    text: str


class RoundQuestionOut(BaseModel):
    id: uuid.UUID
    prompt: str
    question_type: str
    options: list[RoundOptionOut]


class CurrentRoundOut(BaseModel):
    """The active (unresolved) round's question, if there is one — the REST
    fallback for a client that connects to the websocket *after*
    battle.round_released already broadcast (a page refresh, a reconnect,
    switching tabs and back). Without this, the only way to ever learn the
    current question was to have been listening at the exact instant it
    was released, which a refresh could never recover from."""
    round_number: int
    deadline_at: datetime
    question: RoundQuestionOut
    already_answered: bool
    my_is_correct: bool | None
