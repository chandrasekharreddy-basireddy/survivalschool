from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.assessment import AnswerSubmit, OptionPublicOut


class BookmarkCreate(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class BookmarkOut(BaseModel):
    id: uuid.UUID
    question_id: uuid.UUID
    prompt: str
    question_type: str
    note: str | None
    created_at: datetime


class PracticeStartRequest(BaseModel):
    source: str = Field(pattern=r"^(bookmarks|mistakes)$")
    limit: int = Field(default=10, ge=1, le=50)


class PracticeQuestionOut(BaseModel):
    id: uuid.UUID
    prompt: str
    question_type: str
    points: int
    options: list[OptionPublicOut] = []

    model_config = {"from_attributes": True}


class PracticeSessionStartOut(BaseModel):
    id: uuid.UUID
    source: str
    questions: list[PracticeQuestionOut]


class PracticeSubmit(BaseModel):
    answers: list[AnswerSubmit]


class PracticeAnswerResultOut(BaseModel):
    question_id: uuid.UUID
    prompt: str
    is_correct: bool
    selected_option_ids: list[uuid.UUID]
    correct_option_ids: list[uuid.UUID]
    explanation: str | None = None


class PracticeResultOut(BaseModel):
    id: uuid.UUID
    source: str
    score_percent: int
    points_earned: int
    points_possible: int
    submitted_at: datetime | None
    answers: list[PracticeAnswerResultOut] = []


class PracticeSessionHistoryOut(BaseModel):
    id: uuid.UUID
    source: str
    score_percent: int | None
    started_at: datetime
    submitted_at: datetime | None
