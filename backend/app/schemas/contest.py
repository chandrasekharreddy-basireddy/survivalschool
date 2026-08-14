from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.assessment import AnswerSubmit


class ContestOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    contest_type: str
    is_auto_generated: bool
    starts_at: datetime
    ends_at: datetime
    duration_seconds: int
    top_n_awarded: int
    status: str
    question_count: int = 0

    model_config = {"from_attributes": True}


class ContestCreate(BaseModel):
    title: str
    description: str = ""
    starts_at: datetime
    ends_at: datetime
    duration_seconds: int = 1800
    question_ids: list[uuid.UUID]
    top_n_awarded: int = 3


class ContestAttemptStartOut(BaseModel):
    attempt_id: uuid.UUID
    server_deadline_at: datetime
    remaining_seconds: int
    resumed: bool


class ContestSubmit(BaseModel):
    answers: list[AnswerSubmit]


class ContestResultOut(BaseModel):
    id: uuid.UUID
    contest_id: uuid.UUID
    status: str
    score_percent: int | None
    points_earned: int | None
    points_possible: int | None
    rank: int | None
    submitted_at: datetime | None

    model_config = {"from_attributes": True}


class LeaderboardEntryOut(BaseModel):
    rank: int
    student_id: uuid.UUID
    student_name: str
    score_percent: int
    time_taken_seconds: int | None


class ContestCertificateOut(BaseModel):
    certificate_number: str
    contest_id: uuid.UUID
    contest_title: str
    rank: int
    score_percent: int
    issued_at: datetime

    model_config = {"from_attributes": True}
