"""Timetable conflict detection and .ics calendar export.

Real RFC 5545 generation — no third-party calendar library, since the
subset needed here (a handful of VEVENTs with a weekly RRULE) is small
enough to hand-roll correctly and verify directly against the spec, which
also keeps the dependency/vulnerability surface smaller.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models.timetable import TimetableEntry


async def check_conflict(
    db: AsyncSession,
    *,
    instructor_id: uuid.UUID | None,
    room: str,
    term: str,
    day_of_week: int,
    start_time: time,
    end_time: time,
    exclude_entry_id: uuid.UUID | None = None,
) -> None:
    """Raises ConflictError if this slot overlaps an existing entry that
    shares either the same instructor or the same (non-empty) room, on the
    same day of the same term. Two entries "overlap" using the standard
    half-open interval test: A.start < B.end and B.start < A.end."""
    stmt = select(TimetableEntry).where(
        TimetableEntry.term == term,
        TimetableEntry.day_of_week == day_of_week,
        TimetableEntry.start_time < end_time,
        TimetableEntry.end_time > start_time,
    )
    if exclude_entry_id is not None:
        stmt = stmt.where(TimetableEntry.id != exclude_entry_id)

    identity_filters = []
    if instructor_id is not None:
        identity_filters.append(TimetableEntry.instructor_id == instructor_id)
    if room.strip():
        identity_filters.append(TimetableEntry.room == room)
    if not identity_filters:
        return
    stmt = stmt.where(or_(*identity_filters))

    existing = (await db.execute(stmt)).scalars().first()
    if existing is not None:
        clash = "instructor" if existing.instructor_id == instructor_id else "room"
        raise ConflictError(
            f"This slot overlaps an existing timetable entry with a {clash} conflict "
            f"({existing.start_time.strftime('%H:%M')}\u2013{existing.end_time.strftime('%H:%M')})."
        )


def _first_occurrence(term_start: date, day_of_week: int) -> date:
    """First calendar date on/after term_start whose weekday matches
    day_of_week (0=Monday..6=Sunday, matching date.weekday())."""
    delta = (day_of_week - term_start.weekday()) % 7
    return term_start + timedelta(days=delta)


def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def generate_ics(entries: list[TimetableEntry], *, calendar_name: str, course_titles: dict[uuid.UUID, str]) -> str:
    """Builds a real, minimal RFC 5545 calendar: one weekly-recurring VEVENT
    per timetable entry, bounded by that entry's own term dates via RRULE
    UNTIL. A real calendar client (Google Calendar, Outlook, Apple Calendar)
    can import this directly."""
    now_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Survival School//Timetable//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_ics_escape(calendar_name)}",
    ]
    for entry in entries:
        first_date = _first_occurrence(entry.term_start_date, entry.day_of_week)
        dtstart = datetime.combine(first_date, entry.start_time)
        dtend = datetime.combine(first_date, entry.end_time)
        until = datetime.combine(entry.term_end_date, entry.end_time)
        weekday_codes = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
        title = course_titles.get(entry.course_id, "Class")
        summary = f"{title} ({entry.session_type})"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{entry.id}@survivalschool",
            f"DTSTAMP:{now_stamp}",
            f"DTSTART:{dtstart.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{dtend.strftime('%Y%m%dT%H%M%S')}",
            f"RRULE:FREQ=WEEKLY;BYDAY={weekday_codes[entry.day_of_week]};UNTIL={until.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{_ics_escape(summary)}",
            f"LOCATION:{_ics_escape(entry.room or 'TBD')}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    # RFC 5545 requires CRLF line endings.
    return "\r\n".join(lines) + "\r\n"
