from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class OptionCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    is_correct: bool = False
    order_index: int = Field(default=0, ge=0, le=1000)


class QuestionCreate(BaseModel):
    course_id: uuid.UUID | None = None
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


class QuizCreate(BaseModel):
    course_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    # ge=30: a non-positive limit would put every new attempt's deadline in
    # the past the moment it starts. Capped at 24h.
    time_limit_seconds: int | None = Field(default=None, ge=30, le=86400)
    max_attempts: int = Field(default=3, ge=1, le=100)
    randomize_questions: bool = True
    pass_score_percent: int = Field(default=70, ge=0, le=100)
    question_ids: list[uuid.UUID] = Field(default=[], max_length=500)


class QuizOut(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    time_limit_seconds: int | None
    max_attempts: int
    pass_score_percent: int
    is_published: bool

    model_config = {"from_attributes": True}


class AnswerSubmit(BaseModel):
    question_id: uuid.UUID
    selected_option_ids: list[uuid.UUID] = Field(default=[], max_length=20)
    text_answer: str | None = Field(default=None, max_length=10000)


class AttemptSubmit(BaseModel):
    # Bounded so a client can't post an arbitrarily large answer array to the
    # submit endpoint (each entry drives a grading pass and a DB insert).
    answers: list[AnswerSubmit] = Field(max_length=500)
    client_token: str | None = Field(default=None, max_length=128)


class AttemptResultOut(BaseModel):
    id: uuid.UUID
    status: str
    score_percent: int | None
    points_earned: int | None
    points_possible: int | None
    passed: bool | None
    submitted_at: datetime | None

    model_config = {"from_attributes": True}


class ExamCreate(BaseModel):
    course_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    # See QuizCreate: a non-positive limit expires every attempt instantly.
    time_limit_seconds: int = Field(default=3600, ge=30, le=86400)
    max_attempts: int = Field(default=1, ge=1, le=100)
    pass_score_percent: int = Field(default=70, ge=0, le=100)
    question_ids: list[uuid.UUID] = Field(default=[], max_length=500)
    fullscreen_required: bool = False
    integrity_monitoring_enabled: bool = True


class ExamOut(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    time_limit_seconds: int
    max_attempts: int
    pass_score_percent: int
    is_published: bool
    fullscreen_required: bool
    integrity_monitoring_enabled: bool

    model_config = {"from_attributes": True}


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


class AttemptHistoryOut(BaseModel):
    """Used by GET /quizzes/me/attempts and GET /exams/me/attempts — a
    student's own attempt history with the assessment title joined in, so the
    frontend doesn't need N follow-up requests to label each row."""
    id: uuid.UUID
    quiz_id: uuid.UUID | None = None
    exam_id: uuid.UUID | None = None
    title: str
    attempt_number: int
    status: str
    score_percent: int | None
    passed: bool | None
    started_at: datetime
    submitted_at: datetime | None


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
