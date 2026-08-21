"""A student's own uploaded timetable, writing into
personal_timetable_entries, a table scoped to one user with no shared
state. See PersonalTimetableEntry's docstring for why this is deliberately
a separate table rather than a "student mode" on the campus upload path.

Accepts the same simple list-format CSV/XLSX the campus feed does, but
ALSO the real university grid/lab spreadsheet formats
(campus_timetable_service.py) — in practice, the file a student actually
has on hand for "my timetable" is often the whole institution-wide
spreadsheet, not a pre-filtered personal export. For those two formats,
every section's classes get parsed and then filtered down to just the
uploader's own (by profile.section/school — see _filter_to_student), since
importing the entire institution's schedule into one student's personal
view would defeat the point of it being personal.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import time as time_type

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationAppError
from app.models.campus_timetable import PersonalTimetableEntry
from app.services.ai_provider import get_ai_provider
from app.services.campus_timetable_service import (
    _AI_FALLBACK_ERROR_RATE,
    ParsedCampusRow,
    _ai_extract_sheet,
    _detect_format,
    _dicts_from_raw_rows,
    _parse_grid_rows,
    _parse_lab_rows,
)
from app.services.spreadsheet_import import (
    find_column,
    parse_flexible_date,
    parse_flexible_time,
    parse_raw_sheets,
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


def _normalize_section(value: str) -> str:
    """"sec-4", "Section 4", "SEC04", and a bare "4" all mean the same
    section — a profile's section value gets typed in by a person, while
    a real spreadsheet cell's section comes out of _split_class_cell as a
    bare digit string (see campus_timetable_service._SECTION_RE). An
    exact string match between those two is too brittle: it silently
    reduces a real upload to zero rows with no explanation the moment
    someone's profile says "sec-4" instead of "4" (confirmed happening
    to a real user). Strips a leading "sec"/"section" label and leading
    zeros — nothing more exotic than that; this doesn't try to interpret
    arbitrary free text as a section."""
    normalized = re.sub(r"^sec(tion)?[\s.\-]*", "", value.strip().lower())
    return normalized.lstrip("0") or normalized


def _require_section(section: str | None) -> str:
    if not section:
        raise ValidationAppError(
            "This file looks like your institution's full timetable spreadsheet, covering every "
            "section — set your section in your profile first (PATCH /users/me/profile) so we can "
            "pick out just your own classes, then upload it again."
        )
    return _normalize_section(section)


def _require_found_something(parsed: list[ParsedPersonalRow], reduced_any_sheet: bool, section: str) -> None:
    if reduced_any_sheet and not parsed:
        raise ValidationAppError(
            f"This file doesn't have any classes for section \"{section}\" — double-check that your "
            "profile section (Profile settings) matches what the file actually calls your section, "
            "or that you uploaded the right file."
        )


def parse_personal_rows(
    filename: str, content: bytes, *, section: str | None = None, school: str | None = None,
) -> list[ParsedPersonalRow]:
    """Auto-detects the file's shape per sheet, same detection
    campus_timetable_service uses. A plain list-format file (or sheet) is
    parsed directly, unchanged from before. A grid or lab-format sheet —
    what a student's actual copy of the institution's spreadsheet usually
    is — gets parsed the same way the campus importer does and then
    reduced to just this student's own section (see
    _personal_rows_from_campus_rows); section/school come from the
    caller's profile lookup, not from the file itself."""
    sheets = parse_raw_sheets(filename, content)
    section_norm: str | None = None
    school_norm = school.strip().lower() if school else None
    parsed: list[ParsedPersonalRow] = []
    reduced_any_sheet = False
    for raw_rows in sheets:
        fmt = _detect_format(raw_rows)
        if fmt in ("grid", "lab"):
            if section_norm is None:
                section_norm = _require_section(section)
            reduced_any_sheet = True
            campus_rows = _parse_grid_rows(raw_rows) if fmt == "grid" else _parse_lab_rows(raw_rows)
            parsed.extend(_personal_rows_from_campus_rows(campus_rows, section_norm, school_norm))
        else:
            parsed.extend(_personal_rows_from_dicts(_dicts_from_raw_rows(raw_rows)))
    _require_found_something(parsed, reduced_any_sheet, section or "")
    return parsed


async def parse_personal_rows_async(
    filename: str, content: bytes, *, section: str | None = None, school: str | None = None,
) -> list[ParsedPersonalRow]:
    """Async counterpart to parse_personal_rows: on top of everything that
    one handles, a "list"-format sheet that mostly fails to parse (see
    campus_timetable_service._AI_FALLBACK_ERROR_RATE) gets one more
    attempt via AI-assisted extraction — the same fallback the campus
    importer uses for a genuinely clumsy/unrecognized layout, not just
    the three shapes _detect_format knows how to name. AI-extracted rows
    go through the exact same section/school reduction grid/lab rows do
    (see _personal_rows_from_campus_rows) — a sheet only reaches this
    fallback by looking nothing like a real personal export, so it's
    treated the same way an institution-wide file would be."""
    sheets = parse_raw_sheets(filename, content)
    section_norm: str | None = None
    school_norm = school.strip().lower() if school else None
    parsed: list[ParsedPersonalRow] = []
    reduced_any_sheet = False
    for raw_rows in sheets:
        fmt = _detect_format(raw_rows)
        if fmt in ("grid", "lab"):
            if section_norm is None:
                section_norm = _require_section(section)
            reduced_any_sheet = True
            campus_rows = _parse_grid_rows(raw_rows) if fmt == "grid" else _parse_lab_rows(raw_rows)
            parsed.extend(_personal_rows_from_campus_rows(campus_rows, section_norm, school_norm))
            continue
        dict_rows = _personal_rows_from_dicts(_dicts_from_raw_rows(raw_rows))
        if not dict_rows:
            continue
        error_rate = sum(1 for r in dict_rows if r.error) / len(dict_rows)
        if error_rate <= _AI_FALLBACK_ERROR_RATE:
            parsed.extend(dict_rows)
            continue
        ai_campus_rows = await _ai_extract_sheet(raw_rows, get_ai_provider())
        if ai_campus_rows:
            if section_norm is None:
                section_norm = _require_section(section)
            reduced_any_sheet = True
            parsed.extend(_personal_rows_from_campus_rows(ai_campus_rows, section_norm, school_norm))
        else:
            parsed.extend(dict_rows)
    _require_found_something(parsed, reduced_any_sheet, section or "")
    return parsed


def _personal_rows_from_dicts(raw_rows: list[dict[str, str]]) -> list[ParsedPersonalRow]:
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


def _personal_rows_from_campus_rows(
    campus_rows: list[ParsedCampusRow], section_norm: str, school_norm: str | None,
) -> list[ParsedPersonalRow]:
    """section_norm/school_norm are already normalized (see
    _normalize_section) — callers do that once per upload, not per row."""
    parsed: list[ParsedPersonalRow] = []
    for r in campus_rows:
        if _normalize_section(r.section or "") != section_norm:
            continue
        # Same opt-in behavior as the shared campus feed's own /me filter
        # (see campus_timetable.py's my_campus_entries): only applied when
        # the student actually set a school, so grid/lab-derived rows
        # (which never carry a school — see campus_timetable_service.py)
        # aren't silently excluded for accounts that predate this field.
        if school_norm and (r.school or "").strip().lower() != school_norm:
            continue
        parsed.append(ParsedPersonalRow(
            row_number=r.row_number, course_name=r.course_name, course_code=r.course_code,
            class_date=r.class_date, start_time=r.start_time, end_time=r.end_time,
            room=r.room, teacher_name=r.teacher_name, is_elective=r.is_elective,
        ))
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
