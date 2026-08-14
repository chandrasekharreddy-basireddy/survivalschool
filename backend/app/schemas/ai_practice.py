from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AIMockSessionCreate(BaseModel):
    subject: str = Field(min_length=2, max_length=150)
    question_count: int = Field(default=5, ge=3, le=15)


class AIMockOptionOut(BaseModel):
    id: uuid.UUID
    text: str
    order_index: int

    model_config = {"from_attributes": True}


class AIMockQuestionOut(BaseModel):
    id: uuid.UUID
    prompt: str
    options: list[AIMockOptionOut] = []

    model_config = {"from_attributes": True}


class AIMockSessionOut(BaseModel):
    id: uuid.UUID
    subject: str
    question_count: int
    provider: str
    submitted_at: datetime | None
    score_percent: int | None
    questions: list[AIMockQuestionOut] = []

    model_config = {"from_attributes": True}


class AIMockAnswerSubmit(BaseModel):
    question_id: uuid.UUID
    selected_option_ids: list[uuid.UUID] = []


class AIMockSubmit(BaseModel):
    answers: list[AIMockAnswerSubmit]


class AIMockAnswerResultOut(BaseModel):
    question_id: uuid.UUID
    prompt: str
    is_correct: bool
    selected_option_ids: list[uuid.UUID]
    correct_option_ids: list[uuid.UUID]


class AIMockResultOut(BaseModel):
    id: uuid.UUID
    subject: str
    score_percent: int
    answers: list[AIMockAnswerResultOut]


class AIMockSessionHistoryOut(BaseModel):
    id: uuid.UUID
    subject: str
    question_count: int
    submitted_at: datetime | None
    score_percent: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
