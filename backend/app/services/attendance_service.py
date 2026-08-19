from __future__ import annotations

import secrets
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationAppError
from app.models.attendance import AttendanceRecord, AttendanceSession
from app.models.timetable import TimetableEntry

CODE_VALIDITY_MINUTES = 15


def _generate_code() -> str:
    return secrets.token_hex(3).upper()  # 6 hex chars, easy to read aloud/type


async def open_attendance_session(db: AsyncSession, entry: TimetableEntry, opened_by_id) -> AttendanceSession:
    """Opens (or re-opens, rotating the code) today's attendance session for
    a recurring timetable entry. Only valid on the entry's actual scheduled
    day, within the term window — an instructor can't open Monday's
    attendance for a Wednesday-only class."""
    today = date.today()
    if today.weekday() != entry.day_of_week:
        raise ValidationAppError("Today isn't this class's scheduled day — attendance can only be opened on the actual session day.")
    if not (entry.term_start_date <= today <= entry.term_end_date):
        raise ValidationAppError("This class's term isn't currently active.")

    existing = (await db.execute(
        select(AttendanceSession).where(AttendanceSession.timetable_entry_id == entry.id, AttendanceSession.session_date == today)
    )).scalar_one_or_none()
    now = datetime.now(UTC)
    if existing is not None:
        existing.check_in_code = _generate_code()
        existing.code_expires_at = now + timedelta(minutes=CODE_VALIDITY_MINUTES)
        existing.closed_at = None
        await db.commit()
        await db.refresh(existing)
        return existing

    session = AttendanceSession(
        timetable_entry_id=entry.id, session_date=today, opened_by=opened_by_id,
        check_in_code=_generate_code(), code_expires_at=now + timedelta(minutes=CODE_VALIDITY_MINUTES),
    )
    try:
        async with db.begin_nested():
            db.add(session)
            await db.flush()
    except IntegrityError:
        # Lost a race with a concurrent open — re-select what the winner created.
        session = (await db.execute(
            select(AttendanceSession).where(AttendanceSession.timetable_entry_id == entry.id, AttendanceSession.session_date == today)
        )).scalar_one()
    await db.commit()
    await db.refresh(session)
    return session


async def open_or_get_session_for_date(db: AsyncSession, entry: TimetableEntry, session_date: date, opened_by_id) -> AttendanceSession:
    """Like open_attendance_session, but for bulk CSV/XLSX import — an
    instructor digitizing attendance they took on paper needs to target any
    past date that was actually a scheduled session, not just today. Doesn't
    generate/rotate a check-in code since imported sessions aren't meant for
    live student self-check-in."""
    if session_date.weekday() != entry.day_of_week:
        raise ValidationAppError("That date isn't this class's scheduled day of the week.")
    if not (entry.term_start_date <= session_date <= entry.term_end_date):
        raise ValidationAppError("That date falls outside this class's term.")

    existing = (await db.execute(
        select(AttendanceSession).where(AttendanceSession.timetable_entry_id == entry.id, AttendanceSession.session_date == session_date)
    )).scalar_one_or_none()
    if existing is not None:
        return existing

    now = datetime.now(UTC)
    session = AttendanceSession(
        timetable_entry_id=entry.id, session_date=session_date, opened_by=opened_by_id,
        check_in_code=_generate_code(), code_expires_at=now + timedelta(minutes=CODE_VALIDITY_MINUTES),
        closed_at=now,  # imported sessions are already "done" — no live check-in window
    )
    try:
        async with db.begin_nested():
            db.add(session)
            await db.flush()
    except IntegrityError:
        session = (await db.execute(
            select(AttendanceSession).where(AttendanceSession.timetable_entry_id == entry.id, AttendanceSession.session_date == session_date)
        )).scalar_one()
    return session


async def get_valid_session_by_code(db: AsyncSession, code: str) -> AttendanceSession:
    now = datetime.now(UTC)
    session = (await db.execute(
        select(AttendanceSession).where(AttendanceSession.check_in_code == code.upper(), AttendanceSession.closed_at.is_(None))
    )).scalar_one_or_none()
    if session is None or session.code_expires_at < now:
        raise ConflictError("This attendance code is invalid or has expired.")
    return session


async def check_in_with_code(db: AsyncSession, code: str, student_id) -> AttendanceRecord:
    session = await get_valid_session_by_code(db, code)

    existing = (await db.execute(
        select(AttendanceRecord).where(AttendanceRecord.session_id == session.id, AttendanceRecord.student_id == student_id)
    )).scalar_one_or_none()
    if existing is not None:
        return existing

    record = AttendanceRecord(session_id=session.id, student_id=student_id, status="present", method="code")
    try:
        async with db.begin_nested():
            db.add(record)
            await db.flush()
    except IntegrityError:
        record = (await db.execute(
            select(AttendanceRecord).where(AttendanceRecord.session_id == session.id, AttendanceRecord.student_id == student_id)
        )).scalar_one()
    await db.commit()
    await db.refresh(record)
    return record
