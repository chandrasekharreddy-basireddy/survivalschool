from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class SubjectOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str
    is_active: bool
    model_config = {"from_attributes": True}


class SubjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    slug: str = Field(min_length=1, max_length=150, pattern=r"^[a-z0-9-]+$")
    description: str = Field(default="", max_length=2000)


class TopicOut(BaseModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    name: str
    slug: str
    description: str
    is_active: bool
    model_config = {"from_attributes": True}


class TopicCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    slug: str = Field(min_length=1, max_length=150, pattern=r"^[a-z0-9-]+$")
    description: str = Field(default="", max_length=2000)


class TopicDifficultyOut(BaseModel):
    topic_id: uuid.UUID
    difficulty_percent: int
    formula_version: str
    reason: str
    sample_size: int
    eligible_for_ai_exam: bool
