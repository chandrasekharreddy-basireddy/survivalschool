from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BattleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    topic_id: uuid.UUID


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
    model_config = {"from_attributes": True}


class InviteCreate(BaseModel):
    invitee_id: uuid.UUID


class InvitationOut(BaseModel):
    id: uuid.UUID
    battle_id: uuid.UUID
    battle_title: str
    inviter_id: uuid.UUID
    inviter_name: str
    invitee_id: uuid.UUID
    status: str
    created_at: datetime


class ParticipantOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    status: str
    eliminated_at_round: int | None
    eliminated_reason: str | None


class SubmitAnswerIn(BaseModel):
    selected_option_ids: list[uuid.UUID] = Field(default=[], max_length=20)


class SubmitAnswerOut(BaseModel):
    is_correct: bool
    eliminated: bool
