from __future__ import annotations

import uuid
from datetime import date, time

from pydantic import BaseModel, Field, model_validator


class TimetableEntryCreate(BaseModel):
    course_id: uuid.UUID
    term: str = Field(min_length=1, max_length=40)
    term_start_date: date
    term_end_date: date
    day_of_week: int = Field(ge=0, le=6, description="0=Monday .. 6=Sunday")
    start_time: time
    end_time: time
    room: str = ""
    session_type: str = Field(default="lecture", pattern=r"^(lecture|lab|seminar|exam)$")

    @model_validator(mode="after")
    def _validate_ranges(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time.")
        if self.term_end_date <= self.term_start_date:
            raise ValueError("term_end_date must be after term_start_date.")
        return self


class TimetableEntryUpdate(BaseModel):
    term: str | None = Field(default=None, min_length=1, max_length=40)
    term_start_date: date | None = None
    term_end_date: date | None = None
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    start_time: time | None = None
    end_time: time | None = None
    room: str | None = None
    session_type: str | None = Field(default=None, pattern=r"^(lecture|lab|seminar|exam)$")


class TimetableEntryOut(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    course_title: str
    instructor_id: uuid.UUID | None
    instructor_name: str | None
    term: str
    term_start_date: date
    term_end_date: date
    day_of_week: int
    start_time: time
    end_time: time
    room: str
    session_type: str
