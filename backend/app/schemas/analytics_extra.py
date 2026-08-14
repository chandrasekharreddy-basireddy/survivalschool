"""Response models for course-level instructor analytics.

Named analytics_extra.py (not analytics.py) to avoid confusion with
app/services/analytics_service.py (client-event ingestion) and
app/api/v1/analytics.py (that ingestion endpoint) — this module is purely
schemas for the per-course reporting endpoints added to app/api/v1/courses.py.
"""
from __future__ import annotations

import uuid

from pydantic import BaseModel


class QuestionAnalyticsOut(BaseModel):
    question_id: uuid.UUID
    prompt: str
    question_type: str
    times_answered: int
    times_correct: int
    percent_correct: float


class CourseAnalyticsOverviewOut(BaseModel):
    course_id: uuid.UUID
    enrolled_count: int
    completed_count: int
    completion_rate_percent: float
    quiz_attempts_count: int
    exam_attempts_count: int
    average_quiz_score_percent: float | None
    average_exam_score_percent: float | None
    score_distribution: dict[str, int]
