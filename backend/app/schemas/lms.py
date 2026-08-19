from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LessonCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content_type: str = Field(default="article", max_length=30)
    content_body: str = Field(default="", max_length=100000)
    video_url: str | None = Field(default=None, max_length=500)
    order_index: int = Field(default=0, ge=0, le=10000)
    duration_minutes: int = Field(default=5, ge=0, le=1440)


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
    title: str = Field(min_length=1, max_length=200)
    order_index: int = Field(default=0, ge=0, le=10000)


class SectionOut(BaseModel):
    id: uuid.UUID
    title: str
    order_index: int
    lessons: list[LessonOut] = []

    model_config = {"from_attributes": True}


class CourseCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    slug: str = Field(min_length=3, max_length=220, pattern=r"^[a-z0-9-]+$")
    description: str = Field(default="", max_length=20000)
    difficulty: str = Field(default="beginner", pattern=r"^(beginner|intermediate|advanced)$")
    estimated_hours: int = Field(default=0, ge=0, le=10000)
    cover_image_url: str | None = Field(default=None, max_length=500)
    skills: list[str] = Field(default=[], max_length=50)
    specialization: str | None = Field(default=None, max_length=200)


class CourseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=20000)
    difficulty: str | None = Field(default=None, pattern=r"^(beginner|intermediate|advanced)$")
    estimated_hours: int | None = Field(default=None, ge=0, le=10000)
    cover_image_url: str | None = Field(default=None, max_length=500)
    skills: list[str] | None = Field(default=None, max_length=50)
    specialization: str | None = Field(default=None, max_length=200)


class CourseOut(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    description: str
    difficulty: str
    is_published: bool
    estimated_hours: int
    cover_image_url: str | None
    skills: list[str] = []
    specialization: str | None = None
    instructor_id: uuid.UUID | None = None
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
