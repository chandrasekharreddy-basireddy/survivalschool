from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel


class OpenAttendanceSessionIn(BaseModel):
    timetable_entry_id: uuid.UUID


class AttendanceSessionOut(BaseModel):
    id: uuid.UUID
    timetable_entry_id: uuid.UUID
    session_date: date
    check_in_code: str
    code_expires_at: datetime
    closed_at: datetime | None

    model_config = {"from_attributes": True}


class CheckInIn(BaseModel):
    code: str


class AttendanceRecordOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    student_id: uuid.UUID
    student_name: str = ""
    status: str
    method: str
    checked_in_at: datetime

    model_config = {"from_attributes": True}


class ManualMarkIn(BaseModel):
    student_id: uuid.UUID
    status: str  # present|absent|excused


class AttendanceImportSkip(BaseModel):
    row_number: int
    identifier: str
    reason: str


class AttendanceImportOut(BaseModel):
    session: AttendanceSessionOut
    matched_count: int
    created_count: int
    updated_count: int
    skipped: list[AttendanceImportSkip]


class AttendanceSummaryOut(BaseModel):
    course_id: uuid.UUID
    course_title: str
    total_sessions: int
    present_count: int
    attendance_percent: int
