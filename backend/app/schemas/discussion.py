from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ThreadCreate(BaseModel):
    lesson_id: uuid.UUID | None = None
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=1, max_length=10000)


class ReplyCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


class ReplyOut(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID | None
    author_name: str
    body: str
    is_instructor_answer: bool
    created_at: datetime


class ThreadOut(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    lesson_id: uuid.UUID | None
    author_id: uuid.UUID | None
    author_name: str
    title: str
    body: str
    is_resolved: bool
    upvote_count: int
    reply_count: int = 0
    created_at: datetime
    has_voted: bool = False


class ThreadDetailOut(ThreadOut):
    replies: list[ReplyOut] = []
