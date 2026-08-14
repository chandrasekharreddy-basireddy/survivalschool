from __future__ import annotations

import uuid

from pydantic import BaseModel


class SearchResultOut(BaseModel):
    type: str  # course|discussion
    id: uuid.UUID
    title: str
    snippet: str
    course_id: uuid.UUID | None = None
    course_slug: str | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultOut]
