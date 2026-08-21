"""A student's own uploaded timetable — same list-format CSV/XLSX parsing
as the shared campus feed (campus_timetable_service.py), but writing into
personal_timetable_entries, a table scoped to one user with no shared
state. See PersonalTimetableEntry's docstring for why this is deliberately
a separate table rather than a "student mode" on the campus upload path.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import time as time_type

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campus_timetable import PersonalTimetableEntry
from app.services.spreadsheet_import import (
    find_column,
    parse_flexible_date,
    parse_flexible_time,
    parse_tabular_file,
)

_COURSE_NAME_COLS = ["course", "course name", "subject"]
_COURSE_CODE_COLS = ["courseid", "course id", "course_id", "code"]
_DATE_COLS = ["date"]
_START_COLS = ["starttime", "start time", "start_time"]
_END_COLS = ["endtime", "end time", "end_time"]
_ROOM_COLS = ["room"]
_TEACHER_COLS = ["teacher", "faculty", "instructor"]
_ELECTIVE_COLS = ["elective", "is elective"]


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "elective")


@dataclass
class ParsedPersonalRow:
    row_number: int
    course_name: str = ""
    course_code: str | None = None
    class_date: date_type | None = None
    start_time: time_type | None = None
    end_time: time_type | None = None
    room: str | None = None
    teacher_name: str | None = None
    is_elective: bool = False
    error: str | None = None


@dataclass
class PersonalUploadResult:
    total_rows: int = 0
    error_rows: list[dict] = field(default_factory=list)
    imported: int = 0


def parse_personal_rows(filename: str, content: bytes) -> list[ParsedPersonalRow]:
    raw_rows = parse_tabular_file(filename, content)
    parsed: list[ParsedPersonalRow] = []
    for i, raw in enumerate(raw_rows, start=2):  # header is row 1
        row = ParsedPersonalRow(row_number=i)
        row.course_name = find_column(raw, _COURSE_NAME_COLS) or ""
        if not row.course_name:
            row.error = "Missing course name."
            parsed.append(row)
            continue
        date_raw = find_column(raw, _DATE_COLS)
        start_raw = find_column(raw, _START_COLS)
        end_raw = find_column(raw, _END_COLS)
        if not date_raw or not start_raw or not end_raw:
            row.error = "Missing date, start time, or end time."
            parsed.append(row)
            continue
        try:
            row.class_date = parse_flexible_date(date_raw)
            row.start_time = parse_flexible_time(start_raw)
            row.end_time = parse_flexible_time(end_raw)
        except ValueError as e:
            row.error = str(e)
            parsed.append(row)
            continue
        if row.end_time <= row.start_time:
            row.error = "End time must be after start time."
            parsed.append(row)
            continue

        row.course_code = find_column(raw, _COURSE_CODE_COLS)
        row.room = find_column(raw, _ROOM_COLS)
        row.teacher_name = find_column(raw, _TEACHER_COLS)
        row.is_elective = _truthy(find_column(raw, _ELECTIVE_COLS))
        parsed.append(row)
    return parsed


async def replace_personal_timetable(db: AsyncSession, user_id: uuid.UUID, rows: list[ParsedPersonalRow]) -> PersonalUploadResult:
    """All-or-nothing on parse errors, same "fix the file, re-upload"
    contract as the campus importer and the question bulk importer. On
    success, wholesale replaces this user's own rows — see
    PersonalTimetableEntry's docstring for why a diff isn't needed here."""
    result = PersonalUploadResult(total_rows=len(rows))
    error_rows = [r for r in rows if r.error]
    result.error_rows = [{"row_number": r.row_number, "error": r.error} for r in error_rows]
    valid_rows = [r for r in rows if not r.error]
    if error_rows or not valid_rows:
        return result

    await db.execute(delete(PersonalTimetableEntry).where(PersonalTimetableEntry.user_id == user_id))
    for row in valid_rows:
        db.add(PersonalTimetableEntry(
            user_id=user_id, course_name=row.course_name, course_code=row.course_code,
            class_date=row.class_date, day_of_week=row.class_date.weekday(),
            start_time=row.start_time, end_time=row.end_time, room=row.room,
            teacher_name=row.teacher_name, is_elective=row.is_elective,
        ))
    await db.commit()
    result.imported = len(valid_rows)
    return result


async def has_personal_timetable(db: AsyncSession, user_id: uuid.UUID) -> bool:
    return (await db.execute(
        select(PersonalTimetableEntry.id).where(PersonalTimetableEntry.user_id == user_id).limit(1)
    )).scalar_one_or_none() is not None
