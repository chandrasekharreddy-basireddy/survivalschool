from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.assessment import AnswerSubmit


class ClassroomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    subject_id: uuid.UUID | None = None
    section: str = Field(default="", max_length=50)


class ClassroomUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    section: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None


class ClassroomOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    subject_id: uuid.UUID | None
    section: str
    join_code: str
    lecturer_id: uuid.UUID
    lecturer_name: str = ""
    is_active: bool
    member_count: int = 0
    exam_count: int = 0
    created_at: datetime
    model_config = {"from_attributes": True}


class ClassroomJoin(BaseModel):
    join_code: str = Field(min_length=4, max_length=8)


class ClassroomMemberOut(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    student_name: str = ""
    student_email: str = ""
    joined_at: datetime
    model_config = {"from_attributes": True}


class ClassroomExamCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    question_ids: list[uuid.UUID] = Field(default=[], max_length=500)
    duration_seconds: int = Field(default=1800, ge=60, le=86400)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    fullscreen_required: bool = True
    integrity_monitoring_enabled: bool = True
    max_integrity_violations: int = Field(default=5, ge=1, le=50)
    max_warnings_before_terminate: int = Field(default=2, ge=1, le=10)
    face_proctoring_required: bool = False


class ClassroomExamUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    question_ids: list[uuid.UUID] | None = Field(default=None, max_length=500)
    duration_seconds: int | None = Field(default=None, ge=60, le=86400)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    fullscreen_required: bool | None = None
    integrity_monitoring_enabled: bool | None = None
    max_integrity_violations: int | None = Field(default=None, ge=1, le=50)
    max_warnings_before_terminate: int | None = Field(default=None, ge=1, le=10)
    face_proctoring_required: bool | None = None


class ClassroomExamOut(BaseModel):
    id: uuid.UUID
    classroom_id: uuid.UUID
    title: str
    description: str
    question_count: int = 0
    duration_seconds: int
    starts_at: datetime | None
    ends_at: datetime | None
    status: str
    fullscreen_required: bool
    integrity_monitoring_enabled: bool
    max_warnings_before_terminate: int
    face_proctoring_required: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class ClassroomExamAttemptStartOut(BaseModel):
    attempt_id: uuid.UUID
    status: str  # "waiting" (joining closes later, exam hasn't started) | "in_progress"
    exam_starts_at: datetime  # when joining closes and the exam begins for everyone
    server_deadline_at: datetime  # exam_starts_at + duration -- fixed the moment you join
    seconds_until_start: int
    remaining_seconds: int


class MyExamAttemptOut(ClassroomExamAttemptStartOut):
    """Same shape as ClassroomExamAttemptStartOut (status can additionally be
    "submitted"/"terminated" here, not just waiting/in_progress) plus the
    score once there is one -- lets a student who reloads the exam page
    after already finishing see their result instead of a generic
    "exam closed" message with no memory of what they did."""
    score_percent: int | None = None
    points_earned: int | None = None
    points_possible: int | None = None


class ClassroomExamSubmit(BaseModel):
    answers: list[AnswerSubmit] = Field(max_length=500)


class ClassroomExamAttemptOut(BaseModel):
    id: uuid.UUID
    exam_id: uuid.UUID
    student_id: uuid.UUID
    student_name: str = ""
    started_at: datetime
    submitted_at: datetime | None
    time_taken_seconds: int | None
    score_percent: int | None
    points_earned: int | None
    points_possible: int | None
    status: str
    violation_count: int
    warning_count: int
    model_config = {"from_attributes": True}


class IntegrityEventIn(BaseModel):
    event_type: str = Field(max_length=50)
    detail: str = Field(default="", max_length=500)
    device_fingerprint: str | None = Field(default=None, max_length=256)


class IntegrityEventResponse(BaseModel):
    recorded: bool = True
    warning: bool = False
    warnings_remaining: int = 0
    terminated: bool = False
