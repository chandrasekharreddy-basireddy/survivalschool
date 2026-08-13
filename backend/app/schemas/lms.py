from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LessonCreate(BaseModel):
    title: str
    content_type: str = "article"
    content_body: str = ""
    video_url: str | None = None
    order_index: int = 0
    duration_minutes: int = 5


class LessonOut(BaseModel):
    id: uuid.UUID
    title: str
    content_type: str
    content_body: str
    video_url: str | None
    order_index: int
    duration_minutes: int
    is_completed: bool = False

    model_config = {"from_attributes": True}


class SectionCreate(BaseModel):
    title: str
    order_index: int = 0


class SectionOut(BaseModel):
    id: uuid.UUID
    title: str
    order_index: int
    lessons: list[LessonOut] = []

    model_config = {"from_attributes": True}


class CourseCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    slug: str = Field(min_length=3, max_length=220, pattern=r"^[a-z0-9-]+$")
    description: str = ""
    difficulty: str = "beginner"
    estimated_hours: int = 0
    cover_image_url: str | None = None


class CourseUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    difficulty: str | None = None
    estimated_hours: int | None = None
    cover_image_url: str | None = None


class CourseOut(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    description: str
    difficulty: str
    is_published: bool
    estimated_hours: int
    cover_image_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CourseDetailOut(CourseOut):
    sections: list[SectionOut] = []


class EnrollmentOut(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    status: str
    percent_complete: int = 0

    model_config = {"from_attributes": True}
