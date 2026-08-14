from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.assessment import OptionPublicOut


class DailyChallengeQuestionOut(BaseModel):
    id: uuid.UUID
    prompt: str
    question_type: str
    points: int
    options: list[OptionPublicOut] = []

    model_config = {"from_attributes": True}


class DailyChallengeAttemptOut(BaseModel):
    is_correct: bool
    points_awarded: int
    selected_option_ids: list[uuid.UUID]
    correct_option_ids: list[uuid.UUID]


class DailyChallengeOut(BaseModel):
    id: uuid.UUID
    challenge_date: date
    question: DailyChallengeQuestionOut
    already_attempted: bool
    my_attempt: DailyChallengeAttemptOut | None = None
    current_streak_days: int


class DailyChallengeSubmit(BaseModel):
    selected_option_ids: list[uuid.UUID]


class DailyChallengeHistoryEntryOut(BaseModel):
    challenge_date: date
    is_correct: bool
    points_awarded: int
    answered_at: datetime
