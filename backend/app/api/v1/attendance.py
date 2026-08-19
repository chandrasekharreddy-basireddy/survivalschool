from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import AuthorizationError, NotFoundError, ValidationAppError
from app.database import get_db
from app.dependencies import get_current_verified_user, require_permission
from app.models.attendance import AttendanceRecord, AttendanceSession
from app.models.lms import Course, Enrollment
from app.models.timetable import TimetableEntry
from app.models.user import User
from app.schemas.attendance import (
    AttendanceImportOut,
    AttendanceImportSkip,
    AttendanceRecordOut,
    AttendanceSessionOut,
    AttendanceSummaryOut,
    CheckInIn,
    ManualMarkIn,
    OpenAttendanceSessionIn,
)
from app.services.attendance_service import (
    check_in_with_code,
    get_valid_session_by_code,
    open_attendance_session,
    open_or_get_session_for_date,
)
from app.services.audit_service import record_audit_event
from app.services.spreadsheet_import import find_column, parse_tabular_file

router = APIRouter(prefix="/attendance", tags=["attendance"])
settings = get_settings()
_VALID_STATUSES = {"present", "absent", "excused"}


async def _require_course_ownership(db: AsyncSession, user: User, course_id: uuid.UUID) -> Course:
    course = await db.get(Course, course_id)
    if course is None:
        raise NotFoundError("Course not found.")
    if course.instructor_id != user.id and not user.has_permission("system.manage"):
        raise AuthorizationError("You can only manage attendance for your own courses.")
    return course


@router.post("/sessions/open", response_model=AttendanceSessionOut, status_code=201)
async def open_session(payload: OpenAttendanceSessionIn, user: User = Depends(require_permission("timetable.manage")), db: AsyncSession = Depends(get_db)):
    entry = await db.get(TimetableEntry, payload.timetable_entry_id)
    if entry is None:
        raise NotFoundError("Timetable entry not found.")
    await _require_course_ownership(db, user, entry.course_id)
    session = await open_attendance_session(db, entry, user.id)
    await record_audit_event(db, actor_id=user.id, action="attendance.session_opened", resource_type="attendance_session", resource_id=str(session.id))
    # record_audit_event only flushes; without this commit the audit row is
    # rolled back when the request's session closes (get_db doesn't commit on
    # teardown), so every attendance.session_opened event was being silently
    # discarded. open_attendance_session already committed the session itself.
    await db.commit()
    return session


@router.get("/sessions/{session_id}", response_model=list[AttendanceRecordOut])
async def get_session_roster(session_id: uuid.UUID, user: User = Depends(require_permission("timetable.manage")), db: AsyncSession = Depends(get_db)):
    session = await db.get(AttendanceSession, session_id)
    if session is None:
        raise NotFoundError("Attendance session not found.")
    entry = await db.get(TimetableEntry, session.timetable_entry_id)
    await _require_course_ownership(db, user, entry.course_id)

    rows = (await db.execute(
        select(AttendanceRecord, User.full_name).join(User, User.id == AttendanceRecord.student_id)
        .where(AttendanceRecord.session_id == session_id)
    )).all()
    return [
        AttendanceRecordOut(id=r.id, session_id=r.session_id, student_id=r.student_id, student_name=name,
                             status=r.status, method=r.method, checked_in_at=r.checked_in_at)
        for r, name in rows
    ]


@router.post("/sessions/import", response_model=AttendanceImportOut)
async def import_attendance(
    timetable_entry_id: uuid.UUID = Form(...),
    session_date: date = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(require_permission("timetable.manage")),
    db: AsyncSession = Depends(get_db),
):
    """CSV/XLSX roster import: each row's email is matched directly against
    students already actively enrolled in this course — nothing here creates
    accounts or enrollments, it only records attendance for people already
    in the class. A row whose email doesn't match an active enrollment is
    reported back as skipped rather than silently dropped, so the instructor
    can see exactly what didn't map."""
    entry = await db.get(TimetableEntry, timetable_entry_id)
    if entry is None:
        raise NotFoundError("Timetable entry not found.")
    await _require_course_ownership(db, user, entry.course_id)

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValidationAppError(f"File exceeds the {settings.MAX_UPLOAD_MB}MB upload limit.")
    rows = parse_tabular_file(file.filename or "", content)

    enrolled = (await db.execute(
        select(User).join(Enrollment, Enrollment.student_id == User.id)
        .where(Enrollment.course_id == entry.course_id, Enrollment.status == "active")
    )).scalars().all()
    by_email = {u.email.lower(): u for u in enrolled}

    session = await open_or_get_session_for_date(db, entry, session_date, user.id)
    await db.flush()

    existing_records = {
        r.student_id: r
        for r in (await db.execute(select(AttendanceRecord).where(AttendanceRecord.session_id == session.id))).scalars().all()
    }

    created = updated = 0
    skipped: list[AttendanceImportSkip] = []
    for i, row in enumerate(rows, start=2):  # header is row 1
        identifier = find_column(row, ["email", "student email", "e-mail", "mail"])
        if not identifier:
            skipped.append(AttendanceImportSkip(row_number=i, identifier="", reason="No email column found for this row."))
            continue
        status_raw = (find_column(row, ["status", "attendance"]) or "present").strip().lower()
        if status_raw not in _VALID_STATUSES:
            skipped.append(AttendanceImportSkip(row_number=i, identifier=identifier, reason=f"Unrecognized status '{status_raw}'."))
            continue
        student = by_email.get(identifier.strip().lower())
        if student is None:
            skipped.append(AttendanceImportSkip(row_number=i, identifier=identifier, reason="Not an actively enrolled student in this course."))
            continue
        record = existing_records.get(student.id)
        if record is None:
            db.add(AttendanceRecord(session_id=session.id, student_id=student.id, status=status_raw, method="import", marked_by=user.id))
            created += 1
        else:
            record.status = status_raw
            record.method = "import"
            record.marked_by = user.id
            updated += 1

    await record_audit_event(
        db, actor_id=user.id, action="attendance.imported", resource_type="attendance_session",
        resource_id=str(session.id), metadata={"created": created, "updated": updated, "skipped": len(skipped)},
    )
    await db.commit()
    await db.refresh(session)

    return AttendanceImportOut(session=session, matched_count=created + updated, created_count=created, updated_count=updated, skipped=skipped)


@router.post("/check-in", response_model=AttendanceRecordOut)
async def check_in(payload: CheckInIn, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    session = await get_valid_session_by_code(db, payload.code)
    entry = await db.get(TimetableEntry, session.timetable_entry_id)
    enrolled = (await db.execute(
        select(Enrollment).where(Enrollment.course_id == entry.course_id, Enrollment.student_id == user.id, Enrollment.status == "active")
    )).scalar_one_or_none()
    if enrolled is None and not user.has_permission("system.manage"):
        raise AuthorizationError("You're not enrolled in this course.")

    record = await check_in_with_code(db, payload.code, user.id)
    return AttendanceRecordOut(id=record.id, session_id=record.session_id, student_id=record.student_id,
                                student_name=user.full_name, status=record.status, method=record.method,
                                checked_in_at=record.checked_in_at)


@router.post("/sessions/{session_id}/mark", response_model=AttendanceRecordOut)
async def mark_manual(session_id: uuid.UUID, payload: ManualMarkIn, user: User = Depends(require_permission("timetable.manage")), db: AsyncSession = Depends(get_db)):
    session = await db.get(AttendanceSession, session_id)
    if session is None:
        raise NotFoundError("Attendance session not found.")
    entry = await db.get(TimetableEntry, session.timetable_entry_id)
    await _require_course_ownership(db, user, entry.course_id)

    record = (await db.execute(
        select(AttendanceRecord).where(AttendanceRecord.session_id == session_id, AttendanceRecord.student_id == payload.student_id)
    )).scalar_one_or_none()
    if record is None:
        record = AttendanceRecord(session_id=session_id, student_id=payload.student_id, method="manual", marked_by=user.id, status=payload.status)
        db.add(record)
    else:
        record.status = payload.status
        record.method = "manual"
        record.marked_by = user.id
    await db.commit()
    await db.refresh(record)
    student = await db.get(User, payload.student_id)
    return AttendanceRecordOut(id=record.id, session_id=record.session_id, student_id=record.student_id,
                                student_name=student.full_name if student else "", status=record.status,
                                method=record.method, checked_in_at=record.checked_in_at)


@router.get("/me", response_model=list[AttendanceSummaryOut])
async def my_attendance(user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    """Per-course attendance percentage for the calling student, computed
    live from real session/record rows — never a cached or estimated figure."""
    course_ids = (await db.execute(
        select(Enrollment.course_id).where(Enrollment.student_id == user.id, Enrollment.status == "active")
    )).scalars().all()
    if not course_ids:
        return []

    # Batch every step instead of up to 4 queries per enrolled course: one
    # query each for courses, timetable entries (grouped by course),
    # attendance sessions (grouped by entry), and this student's present
    # records — rather than N x 4 sequential round trips.
    courses_by_id = {c.id: c for c in (await db.execute(select(Course).where(Course.id.in_(course_ids)))).scalars().all()}

    entries = (await db.execute(select(TimetableEntry.id, TimetableEntry.course_id).where(TimetableEntry.course_id.in_(course_ids)))).all()
    entry_id_to_course = dict(entries)
    all_entry_ids = list(entry_id_to_course.keys())

    sessions = (await db.execute(
        select(AttendanceSession.id, AttendanceSession.timetable_entry_id).where(AttendanceSession.timetable_entry_id.in_(all_entry_ids))
    )).all() if all_entry_ids else []
    session_ids_by_course: dict[uuid.UUID, list[uuid.UUID]] = {}
    for session_id, timetable_entry_id in sessions:
        course_id = entry_id_to_course.get(timetable_entry_id)
        if course_id is not None:
            session_ids_by_course.setdefault(course_id, []).append(session_id)
    all_session_ids = [s.id for s in sessions]

    present_session_ids: set[uuid.UUID] = set()
    if all_session_ids:
        present_session_ids = set((await db.execute(
            select(AttendanceRecord.session_id).where(
                AttendanceRecord.session_id.in_(all_session_ids),
                AttendanceRecord.student_id == user.id,
                AttendanceRecord.status == "present",
            )
        )).scalars().all())

    summaries = []
    for course_id in course_ids:
        course = courses_by_id.get(course_id)
        if course is None:
            continue
        session_ids = session_ids_by_course.get(course_id, [])
        if not session_ids:
            continue
        present_count = sum(1 for sid in session_ids if sid in present_session_ids)
        summaries.append(AttendanceSummaryOut(
            course_id=course_id, course_title=course.title, total_sessions=len(session_ids),
            present_count=present_count, attendance_percent=round((present_count / len(session_ids)) * 100),
        ))
    return summaries
