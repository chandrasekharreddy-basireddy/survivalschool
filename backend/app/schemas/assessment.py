from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class OptionCreate(BaseModel):
    text: str
    is_correct: bool = False
    order_index: int = 0


class QuestionCreate(BaseModel):
    course_id: uuid.UUID | None = None
    prompt: str
    question_type: str = Field(pattern=r"^(single|multiple|true_false|short_answer)$")
    points: int = 1
    explanation: str | None = None
    short_answer_key: str | None = None
    options: list[OptionCreate] = []


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
    title: str
    time_limit_seconds: int | None = None
    max_attempts: int = 3
    randomize_questions: bool = True
    pass_score_percent: int = 70
    question_ids: list[uuid.UUID] = []


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
    selected_option_ids: list[uuid.UUID] = []
    text_answer: str | None = None


class AttemptSubmit(BaseModel):
    answers: list[AnswerSubmit]
    client_token: str | None = None


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
    title: str
    time_limit_seconds: int = 3600
    max_attempts: int = 1
    pass_score_percent: int = 70
    question_ids: list[uuid.UUID] = []


class ExamOut(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    time_limit_seconds: int
    max_attempts: int
    pass_score_percent: int
    is_published: bool

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
