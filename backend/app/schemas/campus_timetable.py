from __future__ import annotations

import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, Field


class CampusTimetableEntryOut(BaseModel):
    id: uuid.UUID
    school: str | None
    year_of_study: str | None
    section: str
    lab_group: str | None
    course_name: str
    course_code: str | None
    class_date: date
    day_of_week: int
    start_time: time
    end_time: time
    room: str | None
    teacher_name: str | None
    is_elective: bool
    is_cancelled: bool
    source: str

    model_config = {"from_attributes": True}


class CampusImportErrorRow(BaseModel):
    row_number: int
    error: str


class CampusSyncResultOut(BaseModel):
    total_rows: int
    error_rows: list[CampusImportErrorRow]
    created: int
    updated: int
    cancelled: int
    unchanged: int
    change_count: int


class CampusTimetableSourceOut(BaseModel):
    mode: str
    sheet_csv_url: str | None
    poll_interval_minutes: int
    last_synced_at: datetime | None
    last_sync_status: str | None
    last_sync_error: str | None
    last_sync_row_count: int

    model_config = {"from_attributes": True}


class LiveSyncConfigureIn(BaseModel):
    csv_url: str = Field(min_length=8, max_length=2048)
    poll_interval_minutes: int = Field(default=15, ge=5, le=1440)


class CampusSectionOut(BaseModel):
    """One real (school, year, section) combination actually present in the
    uploaded/synced timetable, with its distinct lab groups — lets the
    frontend offer a dropdown of sections that genuinely exist instead of a
    student typing a section name blind and silently seeing nothing."""
    school: str | None
    year_of_study: str | None
    section: str
    lab_groups: list[str]


class PersonalTimetableEntryOut(BaseModel):
    id: uuid.UUID
    course_name: str
    course_code: str | None
    class_date: date
    day_of_week: int
    start_time: time
    end_time: time
    room: str | None
    teacher_name: str | None
    is_elective: bool

    model_config = {"from_attributes": True}


class PersonalUploadResultOut(BaseModel):
    total_rows: int
    error_rows: list[CampusImportErrorRow]
    imported: int


class CampusTeacherOut(BaseModel):
    """One teacher with at least one non-cancelled class in the next 7
    days — class_count/day_count are real distinct-weekly-slot counts
    (see list_campus_teachers), not a raw row count, which would
    over-count by however many weeks ahead each slot is expanded to."""
    teacher_name: str
    class_count: int
    day_count: int


class CampusElectiveSectionOut(BaseModel):
    section: str
    teacher_name: str | None


class CampusElectiveOut(BaseModel):
    course_name: str
    sections: list[CampusElectiveSectionOut]
