"""Campus timetable ingestion: parses rows from an uploaded file or a live
published-CSV URL (see docs on CampusTimetableSource/CampusTimetableEntry in
app/models/campus_timetable.py), diffs them against what's already stored,
and upserts the result. Column names follow the y-bow/SaiU-Timetable
reference sheet: school, year, section, labGroup, course, courseId, day,
date, startTime, endTime, room, teacher, elective.
"""
from __future__ import annotations

import hashlib
import ipaddress
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
    _parse_csv,
    find_column,
    parse_flexible_date,
    parse_flexible_time,
    parse_tabular_file,
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


def parse_campus_rows(filename: str, content: bytes) -> list[ParsedCampusRow]:
    raw_rows = parse_tabular_file(filename, content)
    return _rows_from_dicts(raw_rows)


def parse_campus_csv_bytes(content: bytes) -> list[ParsedCampusRow]:
    # Reuses spreadsheet_import._parse_csv's utf-8-sig/latin-1 fallback so a
    # published Google Sheets CSV export with a BOM or non-UTF8 characters
    # parses the same way here as it does through the manual-upload path
    # (parse_campus_rows -> parse_tabular_file -> the same _parse_csv).
    raw_rows = _parse_csv(content)
    return _rows_from_dicts(raw_rows)


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
