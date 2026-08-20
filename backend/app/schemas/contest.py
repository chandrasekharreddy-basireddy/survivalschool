from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

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
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=20000)
    starts_at: datetime
    ends_at: datetime
    duration_seconds: int = Field(default=1800, ge=30, le=86400)
    question_ids: list[uuid.UUID] = Field(max_length=500)
    top_n_awarded: int = Field(default=3, ge=0, le=100)


class ContestAttemptStartOut(BaseModel):
    attempt_id: uuid.UUID
    server_deadline_at: datetime
    remaining_seconds: int
    resumed: bool


class AIWeeklyRegisterIn(BaseModel):
    subject_id: uuid.UUID
    topic_id: uuid.UUID


class AIWeeklyRegisterOut(BaseModel):
    attempt_id: uuid.UUID
    contest_id: uuid.UUID
    contest_title: str
    starts_at: datetime
    ends_at: datetime
    status: str


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
    expires_at: datetime | None = None
    revoked: bool = False
    verify_url: str | None = None
    model_config = {"from_attributes": True}


class ContestCertificatePublicOut(ContestCertificateOut):
    valid: bool
    student_full_name: str | None = None
    invalid_reason: str | None = None


class ContestCertificateRevokeOut(BaseModel):
    certificate_number: str
    revoked_at: datetime
