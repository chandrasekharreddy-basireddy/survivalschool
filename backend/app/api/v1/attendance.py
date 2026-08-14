from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, NotFoundError
from app.database import get_db
from app.dependencies import get_current_verified_user, require_permission
from app.models.attendance import AttendanceRecord, AttendanceSession
from app.models.lms import Course, Enrollment
from app.models.timetable import TimetableEntry
from app.models.user import User
from app.schemas.attendance import (
    AttendanceRecordOut,
    AttendanceSessionOut,
    AttendanceSummaryOut,
    CheckInIn,
    ManualMarkIn,
    OpenAttendanceSessionIn,
)
from app.services.attendance_service import check_in_with_code, get_valid_session_by_code, open_attendance_session
from app.services.audit_service import record_audit_event

router = APIRouter(prefix="/attendance", tags=["attendance"])


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

    summaries = []
    for course_id in course_ids:
        course = await db.get(Course, course_id)
        if course is None:
            continue
        entry_ids = (await db.execute(select(TimetableEntry.id).where(TimetableEntry.course_id == course_id))).scalars().all()
        if not entry_ids:
            continue
        total = (await db.execute(select(AttendanceSession.id).where(AttendanceSession.timetable_entry_id.in_(entry_ids)))).scalars().all()
        if not total:
            continue
        present = (await db.execute(
            select(AttendanceRecord.id).where(AttendanceRecord.session_id.in_(total), AttendanceRecord.student_id == user.id, AttendanceRecord.status == "present")
        )).scalars().all()
        summaries.append(AttendanceSummaryOut(
            course_id=course_id, course_title=course.title, total_sessions=len(total),
            present_count=len(present), attendance_percent=round((len(present) / len(total)) * 100),
        ))
    return summaries
