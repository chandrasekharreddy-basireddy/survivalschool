from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class OptionCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    is_correct: bool = False
    order_index: int = Field(default=0, ge=0, le=1000)


class QuestionCreate(BaseModel):
    subject_id: uuid.UUID
    topic_id: uuid.UUID
    prompt: str = Field(min_length=1, max_length=10000)
    question_type: str = Field(pattern=r"^(single|multiple|true_false|short_answer)$")
    # ge=1: zero or negative points would violate the DB CHECK constraints on
    # points_possible/points_earned at submit time, turning an instructor's
    # data-entry slip into a 500 for every student taking the assessment.
    points: int = Field(default=1, ge=1, le=1000)
    explanation: str | None = Field(default=None, max_length=10000)
    short_answer_key: str | None = Field(default=None, max_length=2000)
    options: list[OptionCreate] = Field(default=[], max_length=20)


class QuestionOut(BaseModel):
    id: uuid.UUID
    prompt: str
    question_type: str
    points: int

    model_config = {"from_attributes": True}


class OptionPublicOut(BaseModel):
    """Never includes is_correct — sent to students before they answer."""
    id: uuid.UUID
    text: str
    order_index: int

    model_config = {"from_attributes": True}


class QuestionPublicOut(BaseModel):
    id: uuid.UUID
    prompt: str
    question_type: str
    points: int
    options: list[OptionPublicOut] = []

    model_config = {"from_attributes": True}


class AnswerSubmit(BaseModel):
    question_id: uuid.UUID
    selected_option_ids: list[uuid.UUID] = Field(default=[], max_length=20)
    text_answer: str | None = Field(default=None, max_length=10000)


class IntegrityEventIn(BaseModel):
    event_type: str = Field(pattern=r"^(tab_blur|fullscreen_exit|copy|paste|right_click)$")


class FlaggedAttemptOut(BaseModel):
    attempt_id: uuid.UUID
    student_id: uuid.UUID
    student_name: str
    status: str
    score_percent: int | None
    flagged_events: list[dict]

    model_config = {"from_attributes": True}


class ReviewAnswerOut(BaseModel):
    question_id: uuid.UUID
    prompt: str
    question_type: str
    selected_option_ids: list[uuid.UUID]
    correct_option_ids: list[uuid.UUID]
    is_correct: bool | None
    points_awarded: int
    points_possible: int
    explanation: str | None = None


class AttemptReviewOut(BaseModel):
    attempt_id: uuid.UUID
    status: str
    score_percent: int | None
    passed: bool | None
    answers: list[ReviewAnswerOut]
