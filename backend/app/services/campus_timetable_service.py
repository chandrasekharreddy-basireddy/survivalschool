"""Campus timetable ingestion: parses rows from an uploaded file or a live
published-CSV URL (see docs on CampusTimetableSource/CampusTimetableEntry in
app/models/campus_timetable.py), diffs them against what's already stored,
and upserts the result.

Two source shapes are both accepted, auto-detected from the raw rows (see
_detect_format):

  - "list": one row per class, explicit columns. Column names follow the
    y-bow/SaiU-Timetable reference sheet: school, year, section, labGroup,
    course, courseId, day, date, startTime, endTime, room, teacher,
    elective.

  - "grid": what the university actually publishes in practice — a day
    name and time-range per row, one column per room/class-slot, with the
    room name in the row immediately below (see _parse_grid_rows). Same
    layout the y-bow/SaiU-Timetable reference's own grid parser handles,
    ported here since that reference is itself client-side JS and this
    needs a server-side Python equivalent. Grid rows carry a weekday, not
    a calendar date — expanded into concrete class_date occurrences for
    the next _GRID_WEEKS_AHEAD weeks (see CampusTimetableEntry's own
    docstring on why this model is date-based, not a recurring slot).

  - "lab": a third shape unique to per-lab schedule sheets (the real Sai
    University workbook ships one grid-format "main schedule" sheet plus
    several of these, one per lab course) — an explicit "Day | Time |
    Section" header, then day/time rows with a single class-slot column
    holding a combined "<course prefix> Sec<N> <faculty>" cell and no room
    at all (see _parse_lab_rows). The course itself comes from the sheet's
    own title row, not from any column. When the uploaded file is an
    .xlsx workbook with more than one sheet, every sheet is parsed (each
    independently format-detected) and the results concatenated — a
    single upload is the only way a user can submit this file, so it has
    to account for all of its sheets, not just the first.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from datetime import time as time_type
from urllib.parse import urlparse

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationAppError
from app.database import AsyncSessionLocal
from app.models.campus_timetable import CampusTimetableEntry, CampusTimetableSource
from app.services.n8n_service import emit_event
from app.services.spreadsheet_import import (
    _parse_csv_raw,
    find_column,
    parse_flexible_date,
    parse_flexible_time,
    parse_raw_sheets,
)

logger = structlog.get_logger("survivalschool.campus_timetable")

_SECTION_COLS = ["section", "sec"]
_SCHOOL_COLS = ["school"]
_YEAR_COLS = ["year", "academic year", "academicyear"]
_LAB_GROUP_COLS = ["labgroup", "lab group", "lab_group"]
_COURSE_NAME_COLS = ["course", "course name", "subject"]
_COURSE_CODE_COLS = ["courseid", "course id", "course_id", "code"]
_DATE_COLS = ["date"]
_START_COLS = ["starttime", "start time", "start_time"]
_END_COLS = ["endtime", "end time", "end_time"]
_ROOM_COLS = ["room"]
_TEACHER_COLS = ["teacher", "faculty", "instructor"]
_ELECTIVE_COLS = ["elective", "is elective"]


@dataclass
class ParsedCampusRow:
    row_number: int
    school: str | None = None
    year_of_study: str | None = None
    section: str = ""
    lab_group: str | None = None
    course_name: str = ""
    course_code: str | None = None
    class_date: date_type | None = None
    start_time: time_type | None = None
    end_time: time_type | None = None
    room: str | None = None
    teacher_name: str | None = None
    is_elective: bool = False
    error: str | None = None


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "elective")


_LIST_HEADER_HINTS = {
    "day", "date", "weekday", "time", "starttime", "start time", "start_time",
    "subject", "course", "course name",
}
_WEEKDAY_INDEX = {
    "MONDAY": 0, "TUESDAY": 1, "WEDNESDAY": 2, "THURSDAY": 3,
    "FRIDAY": 4, "SATURDAY": 5, "SUNDAY": 6,
}


def _detect_format(raw_rows: list[list[str]]) -> str:
    """A list-format file's header row directly names its columns. A lab
    sheet has its own explicit "Day | Time | Section" header — checked
    before the grid scan below, since a lab sheet's later day/time rows
    would otherwise also trip the grid check. A grid file's day names only
    show up a few rows down (after a title/school row) with no header row
    of their own at all, so a header check alone would misclassify it as
    neither — check for that shape too before falling back to "list"
    (which then surfaces the normal "missing section or course name"
    per-row errors rather than silently emitting nothing)."""
    for row in raw_rows[:5]:
        if (
            len(row) > 2
            and row[0].strip().lower() == "day"
            and row[1].strip().lower().startswith("time")
            and row[2].strip().lower().startswith("section")
        ):
            return "lab"
    if raw_rows:
        header_hit = {c.strip().lower() for c in raw_rows[0] if c} & _LIST_HEADER_HINTS
        if header_hit:
            return "list"
    for row in raw_rows[:15]:
        if row and row[0].strip().upper() in _WEEKDAY_INDEX:
            return "grid"
    return "list"


def _parse_one_sheet(raw_rows: list[list[str]]) -> list[ParsedCampusRow]:
    fmt = _detect_format(raw_rows)
    if fmt == "grid":
        return _parse_grid_rows(raw_rows)
    if fmt == "lab":
        return _parse_lab_rows(raw_rows)
    return _rows_from_dicts(_dicts_from_raw_rows(raw_rows))


def parse_campus_rows(filename: str, content: bytes) -> list[ParsedCampusRow]:
    sheets = parse_raw_sheets(filename, content)
    parsed: list[ParsedCampusRow] = []
    for raw_rows in sheets:
        parsed.extend(_parse_one_sheet(raw_rows))
    return parsed


def parse_campus_csv_bytes(content: bytes) -> list[ParsedCampusRow]:
    # Reuses spreadsheet_import._parse_csv_raw's utf-8-sig/latin-1 fallback
    # so a published Google Sheets CSV export with a BOM or non-UTF8
    # characters parses the same way here as it does through the
    # manual-upload path (parse_campus_rows -> parse_raw_sheets -> the
    # same underlying CSV reader). A CSV only ever has the one sheet.
    raw_rows = _parse_csv_raw(content)
    return _parse_one_sheet(raw_rows)


def _dicts_from_raw_rows(raw_rows: list[list[str]]) -> list[dict[str, str]]:
    if not raw_rows:
        return []
    headers = [c.strip().lower() for c in raw_rows[0]]
    return [
        {headers[i]: (row[i] if i < len(row) else "") for i in range(len(headers)) if headers[i]}
        for row in raw_rows[1:]
    ]


_SECTION_RE = re.compile(r"Sec\s*\.?\s*(\d+)", re.IGNORECASE)
_SECTION_STRIP_RE1 = re.compile(r"\s*\(Sec\s*\.?\s*\d+\)\s*", re.IGNORECASE)
_SECTION_STRIP_RE2 = re.compile(r"\s*-\s*Sec\s*\.?\s*\d+\s*-?\s*", re.IGNORECASE)
_GRID_TIME_RANGE_RE = re.compile(
    r"(\d{1,2})[:.](\d{2})\s*(AM|PM)?\s*-\s*(\d{1,2})[:.](\d{2})\s*(AM|PM)?", re.IGNORECASE
)
_GRID_WEEKS_AHEAD = 8


def _split_class_cell(cell: str) -> tuple[str, str, str | None]:
    """Mirrors the core of y-bow/SaiU-Timetable's splitSubjectFaculty: a
    grid cell reads "Subject - Sec N - Faculty" or, for schools that don't
    section this way, "Subject    Faculty" separated by a run of 2+
    spaces rather than a dash at all (e.g. real data seen in this sheet:
    "Analytical Methods & Instrumentation    Manobala").

    Critically, section-marker stripping must NOT collapse that run of
    spaces before the split runs — an earlier version of this function did
    (via a single `\\s+` → single-space pass shared with the section-marker
    strip), which silently glued every such faculty name onto its subject.
    The reference's own comment on this exact bug: "collapsing it here (as
    the old strip did) destroyed 'Differential Equations         ArunKumar'
    before splitSubjectFaculty could use the spacing as the separator."
    This port skips the reference's further known-course-database-driven
    refinements (no such catalog is available here) but keeps the fix that
    actually matters for this sheet's data.
    """
    section_match = _SECTION_RE.search(cell)
    section = section_match.group(1) if section_match else None
    # Strip section/semester markers WITHOUT collapsing other whitespace.
    text = _SECTION_STRIP_RE1.sub(" ", cell)
    text = _SECTION_STRIP_RE2.sub(" - ", text)
    text = text.strip()

    parts = [p.strip() for p in re.split(r"\s{2,}", text) if p.strip()]
    subject = parts[0] if parts else ""
    faculty = " ".join(parts[1:])

    # "Subject - Faculty" dash form, only when the multi-space split above
    # didn't already isolate a faculty name.
    if not faculty and " - " in subject:
        subject, faculty = (p.strip() for p in subject.split(" - ", 1))

    # Now safe to collapse any remaining internal whitespace runs (e.g. a
    # subject that itself had irregular spacing) — the split that needed
    # the raw spacing has already happened.
    subject = re.sub(r"\s+", " ", subject).strip()
    faculty = re.sub(r"\s+", " ", faculty).strip()
    return subject, faculty, section


def _parse_grid_time_range(text: str) -> tuple[time_type, time_type]:
    m = _GRID_TIME_RANGE_RE.search(text)
    if not m:
        raise ValueError(f"Unrecognized time range: {text!r}")
    h1, m1, ap1, h2, m2, ap2 = m.groups()
    # AM/PM is sometimes only written once when both ends share the same
    # period ("11.15 AM - 12.10 PM" always has both, but be lenient) —
    # infer the missing side from its sibling rather than assuming 24h.
    ap1, ap2 = ap1 or ap2, ap2 or ap1
    return _grid_to_24h(h1, m1, ap1), _grid_to_24h(h2, m2, ap2)


def _grid_to_24h(hour_str: str, minute_str: str, meridiem: str | None) -> time_type:
    hour, minute = int(hour_str), int(minute_str)
    if meridiem:
        meridiem = meridiem.upper()
        if meridiem == "PM" and hour != 12:
            hour += 12
        elif meridiem == "AM" and hour == 12:
            hour = 0
    return time_type(hour % 24, minute)


def _next_weekday_occurrence(today: date_type, weekday_idx: int, week_offset: int) -> date_type:
    days_ahead = (weekday_idx - today.weekday()) % 7
    return today + timedelta(days=days_ahead + 7 * week_offset)


def _parse_grid_rows(raw_rows: list[list[str]]) -> list[ParsedCampusRow]:
    """Grid-format layout: col 0 carries the day name only on the first row
    of that day (blank/carried-forward after), col 1 the time range, col 2+
    one class-slot cell per column — with that same column's *room* given
    in the very next non-blank row. Deliberately lenient (no per-row
    "error" entries the way _rows_from_dicts has) to match how messy real
    scheduling spreadsheets are: a cell with no recognizable room or
    subject is just skipped rather than failing the whole import."""
    parsed: list[ParsedCampusRow] = []
    today = date_type.today()
    current_day_idx: int | None = None

    for i, row in enumerate(raw_rows):
        row_number = i + 1
        if not row or not any(c.strip() for c in row if c):
            continue
        col0 = (row[0] or "").strip().upper()
        if col0 in _WEEKDAY_INDEX:
            current_day_idx = _WEEKDAY_INDEX[col0]
        if current_day_idx is None:
            continue

        time_text = row[1] if len(row) > 1 else ""
        if not time_text:
            continue
        # "LUNCH BREAK" / "OPEN BLOCK" markers show up as an ordinary class
        # cell (typically column 2), not inside the time range text itself
        # — checking only time_text (as the reference parser this is based
        # on does) misses them entirely in this data, which then makes the
        # room-row lookup below skip past the following blank row into the
        # *next real class row* and misattribute its subjects as "rooms"
        # for the break slot. Check every cell in the row instead.
        if any(re.search(r"LUNCH|OPEN\s*BLOCK", c, re.IGNORECASE) for c in row if c):
            continue
        try:
            start_time, end_time = _parse_grid_time_range(time_text)
        except ValueError:
            continue
        if end_time <= start_time:
            continue

        room_row = None
        for candidate in raw_rows[i + 1:]:
            if candidate and any(c.strip() for c in candidate if c):
                room_row = candidate
                break

        if room_row is None:
            continue

        width = max(len(row), len(room_row))
        for col_idx in range(2, width):
            room_val = (room_row[col_idx].strip() if col_idx < len(room_row) else "")
            if not room_val:
                continue
            cell = row[col_idx].strip() if col_idx < len(row) else ""
            if not cell:
                continue
            subject, faculty, section = _split_class_cell(cell)
            if not subject:
                continue
            for week in range(_GRID_WEEKS_AHEAD):
                parsed.append(ParsedCampusRow(
                    row_number=row_number,
                    section=section or "1",
                    course_name=subject,
                    class_date=_next_weekday_occurrence(today, current_day_idx, week),
                    start_time=start_time, end_time=end_time,
                    room=room_val.replace("  ", " "),
                    teacher_name=faculty or None,
                ))
    return parsed


_LAB_TITLE_CODE_RE = re.compile(r"\(([A-Z]{2,}\d{2,})\)")
_LAB_CELL_RE = re.compile(r"^\S+\s+Sec\.?\s*(\d+)\s*(.*)$", re.IGNORECASE)


def _lab_course_name_and_code(title: str) -> tuple[str, str | None]:
    """A lab sheet's title row (its own row 0, e.g. "Design and Analysis of
    Algorithms Lab (CS324) Schedule From 10-August-2026") carries the
    course itself — there's no per-row course column the way the other two
    formats have one. Take everything before "(CODE)" when present, else
    strip a trailing "Schedule..." tail."""
    code_match = _LAB_TITLE_CODE_RE.search(title)
    if code_match:
        return title[:code_match.start()].strip(), code_match.group(1)
    return re.sub(r"\s*\bSchedule\b.*$", "", title, flags=re.IGNORECASE).strip(), None


def _parse_lab_rows(raw_rows: list[list[str]]) -> list[ParsedCampusRow]:
    """Lab-sheet layout: an explicit "Day | Time | Section" header (see
    _detect_format), then day/time rows with a single class-slot column
    (col 2) holding a combined "<prefix> Sec<N> <faculty>" cell — e.g.
    "DAA Sec2 david" or "DAA Sec 8 Rupam Sah" — and, unlike the grid
    format, no room anywhere in the sheet at all. The course itself comes
    from the sheet's own title (raw_rows[0][0]), not from any column.
    Deliberately conservative: a section cell that doesn't match the
    "<prefix> Sec<N> <faculty>" shape is skipped rather than guessed at,
    same philosophy as _parse_grid_rows."""
    if not raw_rows:
        return []
    course_name, course_code = _lab_course_name_and_code(raw_rows[0][0] if raw_rows[0] else "")
    if not course_name:
        return []

    parsed: list[ParsedCampusRow] = []
    today = date_type.today()
    current_day_idx: int | None = None

    for i, row in enumerate(raw_rows):
        row_number = i + 1
        if not row or not any(c.strip() for c in row if c):
            continue
        col0 = (row[0] or "").strip().upper()
        if col0 in _WEEKDAY_INDEX:
            current_day_idx = _WEEKDAY_INDEX[col0]
        if current_day_idx is None:
            continue

        time_text = row[1] if len(row) > 1 else ""
        section_cell = row[2].strip() if len(row) > 2 and row[2] else ""
        if not time_text or not section_cell:
            continue
        if re.search(r"LUNCH|OPEN\s*BLOCK", section_cell, re.IGNORECASE):
            continue
        try:
            start_time, end_time = _parse_grid_time_range(time_text)
        except ValueError:
            continue
        if end_time <= start_time:
            continue

        match = _LAB_CELL_RE.match(section_cell)
        if not match:
            continue
        section, faculty = match.group(1), match.group(2).strip()
        for week in range(_GRID_WEEKS_AHEAD):
            parsed.append(ParsedCampusRow(
                row_number=row_number,
                section=section,
                course_name=course_name,
                course_code=course_code,
                class_date=_next_weekday_occurrence(today, current_day_idx, week),
                start_time=start_time, end_time=end_time,
                room=None,
                teacher_name=faculty or None,
            ))
    return parsed


def _rows_from_dicts(raw_rows: list[dict[str, str]]) -> list[ParsedCampusRow]:
    parsed: list[ParsedCampusRow] = []
    for i, raw in enumerate(raw_rows, start=2):  # header is row 1
        row = ParsedCampusRow(row_number=i)
        row.section = find_column(raw, _SECTION_COLS) or ""
        row.course_name = find_column(raw, _COURSE_NAME_COLS) or ""
        if not row.section or not row.course_name:
            row.error = "Missing section or course name."
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

        row.school = find_column(raw, _SCHOOL_COLS)
        row.year_of_study = find_column(raw, _YEAR_COLS)
        row.lab_group = find_column(raw, _LAB_GROUP_COLS)
        row.course_code = find_column(raw, _COURSE_CODE_COLS)
        row.room = find_column(raw, _ROOM_COLS)
        row.teacher_name = find_column(raw, _TEACHER_COLS)
        row.is_elective = _truthy(find_column(raw, _ELECTIVE_COLS))
        parsed.append(row)
    return parsed


def _row_key(row: ParsedCampusRow, source: str) -> str:
    # school + section, never section alone — per y-bow/SaiU-Timetable's own
    # README ("group identity is school + section"): section numbers repeat
    # across schools (e.g. both an "SCDS Section 3" and an "SOAI Section 3"
    # can exist), so section alone isn't a stable identity and would let two
    # unrelated schools' rows collide onto the same row_key.
    #
    # source is also part of the identity: row_key has a single global
    # UniqueConstraint (not composite with source), and apply_campus_rows()
    # only ever compares incoming rows against existing rows from the *same*
    # source. Without source in the hash, an "upload" row and a "live_sync"
    # row for the identical class/date/time would produce the same key, be
    # invisible to each other's existing-row lookup, and collide on INSERT
    # with an uncaught IntegrityError — exactly the case the class docstring
    # ("entries from different sources are tracked separately") promises
    # doesn't happen.
    identity = "|".join([
        source,
        (row.school or "").strip().lower(),
        (row.section or "").strip().lower(),
        (row.course_code or row.course_name or "").strip().lower(),
        row.class_date.isoformat(),
        row.start_time.isoformat(),
    ])
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _row_hash(row: ParsedCampusRow, is_cancelled: bool = False) -> str:
    content = "|".join([
        row.end_time.isoformat(),
        (row.room or "").strip().lower(),
        (row.teacher_name or "").strip().lower(),
        str(row.is_elective),
        str(is_cancelled),
    ])
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class SyncResult:
    total_rows: int = 0
    error_rows: list[dict] = field(default_factory=list)
    created: int = 0
    updated: int = 0
    cancelled: int = 0
    unchanged: int = 0
    changes: list[dict] = field(default_factory=list)


async def apply_campus_rows(db: AsyncSession, rows: list[ParsedCampusRow], source: str) -> SyncResult:
    """All-or-nothing on parse errors: if any row failed to parse, nothing is
    written — same "fix the file, re-upload" contract as the question bulk
    importer. Once rows are valid, upserts by row_key and soft-cancels
    previously-known entries that fall inside this batch's date range but
    are no longer present in it."""
    result = SyncResult(total_rows=len(rows))
    error_rows = [r for r in rows if r.error]
    result.error_rows = [{"row_number": r.row_number, "error": r.error} for r in error_rows]
    valid_rows = [r for r in rows if not r.error]
    if error_rows or not valid_rows:
        return result

    incoming_by_key = {_row_key(r, source): r for r in valid_rows}
    min_date = min(r.class_date for r in valid_rows)
    max_date = max(r.class_date for r in valid_rows)

    existing = (await db.execute(
        select(CampusTimetableEntry).where(
            CampusTimetableEntry.class_date >= min_date,
            CampusTimetableEntry.class_date <= max_date,
            CampusTimetableEntry.source == source,
        )
    )).scalars().all()
    existing_by_key = {e.row_key: e for e in existing}

    for key, row in incoming_by_key.items():
        new_hash = _row_hash(row)
        existing_entry = existing_by_key.get(key)
        if existing_entry is None:
            db.add(CampusTimetableEntry(
                row_key=key, row_hash=new_hash, school=row.school, year_of_study=row.year_of_study,
                section=row.section, lab_group=row.lab_group, course_name=row.course_name,
                course_code=row.course_code, class_date=row.class_date, day_of_week=row.class_date.weekday(),
                start_time=row.start_time, end_time=row.end_time, room=row.room, teacher_name=row.teacher_name,
                is_elective=row.is_elective, is_cancelled=False, source=source,
            ))
            result.created += 1
        elif existing_entry.row_hash != new_hash or existing_entry.is_cancelled:
            change = {
                "section": row.section, "course": row.course_name, "date": row.class_date.isoformat(),
                "old_room": existing_entry.room, "new_room": row.room,
                "old_time": f"{existing_entry.start_time}-{existing_entry.end_time}",
                "new_time": f"{row.start_time}-{row.end_time}",
                "was_cancelled": existing_entry.is_cancelled,
            }
            existing_entry.row_hash = new_hash
            existing_entry.school = row.school
            existing_entry.year_of_study = row.year_of_study
            existing_entry.lab_group = row.lab_group
            existing_entry.course_name = row.course_name
            existing_entry.course_code = row.course_code
            existing_entry.start_time = row.start_time
            existing_entry.end_time = row.end_time
            existing_entry.room = row.room
            existing_entry.teacher_name = row.teacher_name
            existing_entry.is_elective = row.is_elective
            existing_entry.is_cancelled = False
            result.updated += 1
            result.changes.append(change)
        else:
            result.unchanged += 1

    for key, existing_entry in existing_by_key.items():
        if key not in incoming_by_key and not existing_entry.is_cancelled:
            existing_entry.is_cancelled = True
            existing_entry.row_hash = _row_hash_for_cancel(existing_entry)
            result.cancelled += 1
            result.changes.append({
                "section": existing_entry.section, "course": existing_entry.course_name,
                "date": existing_entry.class_date.isoformat(), "cancelled": True,
            })

    if result.changes:
        await emit_event("campus_timetable.changed", {"source": source, "change_count": len(result.changes), "changes": result.changes[:50]})

    return result


def _row_hash_for_cancel(entry: CampusTimetableEntry) -> str:
    content = "|".join([entry.end_time.isoformat(), (entry.room or "").strip().lower(),
                         (entry.teacher_name or "").strip().lower(), str(entry.is_elective), "True"])
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class UnsafeUrlError(ValidationAppError):
    pass


def _validate_external_url(url: str) -> None:
    """SSRF guard for the live-sync URL: only https, only a real public
    hostname whose resolved IP isn't private/loopback/link-local. This URL
    is fetched server-side on a recurring schedule, so anything laxer here
    is an internal-network probe waiting to happen."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise UnsafeUrlError("The timetable URL must use https.")
    if not parsed.hostname:
        raise UnsafeUrlError("The timetable URL is missing a host.")
    try:
        addrs = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as e:
        raise UnsafeUrlError("Couldn't resolve that host.") from e
    for _family, _type, _proto, _canonname, sockaddr in addrs:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise UnsafeUrlError("That host resolves to a non-public address and can't be used.")


async def fetch_and_apply_live_sync(db: AsyncSession, csv_url: str) -> SyncResult:
    # Redirects are refused rather than followed: a URL that passed the host
    # check above could otherwise 302 to an internal address at fetch time.
    _validate_external_url(csv_url)
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
        resp = await client.get(csv_url)
        if resp.is_redirect:
            raise UnsafeUrlError("That URL redirects, which isn't allowed for the live-sync source.")
        resp.raise_for_status()
    rows = parse_campus_csv_bytes(resp.content)
    return await apply_campus_rows(db, rows, source="live_sync")


async def sync_campus_timetable_if_due() -> None:
    """Housekeeping job (see scheduler_runtime._run_housekeeping) — polls the
    configured live-sync URL, but only once its own poll_interval_minutes
    has actually elapsed since the last sync. The housekeeping tick calls
    this far more often than that; this function is what makes the interval
    real, not the tick's own cadence."""
    async with AsyncSessionLocal() as db:
        source = (await db.execute(select(CampusTimetableSource).where(CampusTimetableSource.singleton.is_(True)))).scalar_one_or_none()
        if source is None or source.mode != "live_sync" or not source.sheet_csv_url:
            return
        now = datetime.now(UTC)
        if source.last_synced_at is not None and now - source.last_synced_at < timedelta(minutes=source.poll_interval_minutes):
            return

        csv_url = source.sheet_csv_url
    async with AsyncSessionLocal() as db:
        source = (await db.execute(select(CampusTimetableSource).where(CampusTimetableSource.singleton.is_(True)))).scalar_one()
        try:
            result = await fetch_and_apply_live_sync(db, csv_url)
            source.last_synced_at = datetime.now(UTC)
            source.last_sync_status = "error" if result.error_rows else "ok"
            source.last_sync_error = f"{len(result.error_rows)} row(s) failed to parse." if result.error_rows else None
            source.last_sync_row_count = result.total_rows
            await db.commit()
            logger.info("campus_timetable_synced", created=result.created, updated=result.updated, cancelled=result.cancelled)
        except Exception as e:
            source.last_synced_at = datetime.now(UTC)
            source.last_sync_status = "error"
            source.last_sync_error = str(e)[:500]
            await db.commit()
            logger.warning("campus_timetable_sync_failed", error=str(e))
