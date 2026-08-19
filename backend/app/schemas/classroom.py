from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AttachmentIn(BaseModel):
    file_id: uuid.UUID
    title: str = Field(max_length=200)


# ---- Stream ----

class AnnouncementCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    is_pinned: bool = False


class AnnouncementOut(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    author_id: uuid.UUID | None
    author_name: str
    body: str
    is_pinned: bool
    comment_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class AnnouncementCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class AnnouncementCommentOut(BaseModel):
    id: uuid.UUID
    announcement_id: uuid.UUID
    author_id: uuid.UUID | None
    author_name: str
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- Classwork ----

class AssignmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(default="", max_length=10000)
    due_at: datetime | None = None
    points_possible: int = Field(default=100, ge=0, le=1000)
    is_published: bool = True
    attachments: list[AttachmentIn] = Field(default_factory=list)


class AssignmentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    instructions: str | None = Field(default=None, max_length=10000)
    due_at: datetime | None = None
    points_possible: int | None = Field(default=None, ge=0, le=1000)
    is_published: bool | None = None


class AssignmentOut(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    instructions: str
    due_at: datetime | None
    points_possible: int
    is_published: bool
    attachments: list[dict]
    created_at: datetime
    # Present only for the calling student — their own submission status, so
    # a classwork list can show "Assigned / Submitted / Graded" without a
    # second round trip per assignment.
    my_status: str | None = None
    my_grade: int | None = None

    model_config = {"from_attributes": True}


class SubmissionSubmit(BaseModel):
    content: str = Field(default="", max_length=20000)
    attachments: list[AttachmentIn] = Field(default_factory=list)


class GradeIn(BaseModel):
    grade: int = Field(ge=0)
    feedback: str | None = Field(default=None, max_length=5000)


class SubmissionOut(BaseModel):
    id: uuid.UUID
    assignment_id: uuid.UUID
    student_id: uuid.UUID
    student_name: str
    content: str
    attachments: list[dict]
    status: str
    submitted_at: datetime | None
    grade: int | None
    feedback: str | None
    graded_at: datetime | None

    model_config = {"from_attributes": True}


class SubmissionCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class SubmissionCommentOut(BaseModel):
    id: uuid.UUID
    submission_id: uuid.UUID
    author_id: uuid.UUID | None
    author_name: str
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- People ----

class RosterMemberOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str
    role: str  # instructor|student


# ---- Grades ----

class GradebookRowOut(BaseModel):
    student_id: uuid.UUID
    student_name: str
    grades: dict[str, int | None]  # assignment_id (str) -> grade
    total_earned: int
    total_possible: int


class GradebookOut(BaseModel):
    assignments: list[AssignmentOut]
    rows: list[GradebookRowOut]
