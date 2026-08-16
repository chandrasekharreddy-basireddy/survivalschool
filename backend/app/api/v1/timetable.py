from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationAppError
from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.lms import Course, Enrollment
from app.models.timetable import TimetableEntry
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.timetable import TimetableEntryCreate, TimetableEntryOut, TimetableEntryUpdate
from app.services.audit_service import record_audit_event
from app.services.timetable_service import check_conflict, generate_ics

router = APIRouter(prefix="/timetable", tags=["timetable"])


async def _require_course_ownership(db: AsyncSession, user: User, course_id: uuid.UUID) -> Course:
    course = await db.get(Course, course_id)
    if course is None:
        raise NotFoundError("Course not found.")
    if course.instructor_id != user.id and not user.has_permission("system.manage"):
        raise AuthorizationError("You can only manage the timetable for your own courses.")
    return course


async def _to_out(db: AsyncSession, entry: TimetableEntry) -> TimetableEntryOut:
    course = await db.get(Course, entry.course_id)
    instructor = await db.get(User, entry.instructor_id) if entry.instructor_id else None
    return TimetableEntryOut(
        id=entry.id, course_id=entry.course_id, course_title=course.title if course else "Unknown course",
        instructor_id=entry.instructor_id, instructor_name=instructor.full_name if instructor else None,
        term=entry.term, term_start_date=entry.term_start_date, term_end_date=entry.term_end_date,
        day_of_week=entry.day_of_week, start_time=entry.start_time, end_time=entry.end_time,
        room=entry.room, session_type=entry.session_type,
    )


@router.post("", response_model=TimetableEntryOut, status_code=201)
async def create_entry(
    payload: TimetableEntryCreate,
    user: User = Depends(require_permission("timetable.manage")),
    db: AsyncSession = Depends(get_db),
):
    course = await _require_course_ownership(db, user, payload.course_id)
    instructor_id = course.instructor_id
    await check_conflict(
        db, instructor_id=instructor_id, room=payload.room, term=payload.term,
        day_of_week=payload.day_of_week, start_time=payload.start_time, end_time=payload.end_time,
    )
    entry = TimetableEntry(
        course_id=payload.course_id, instructor_id=instructor_id, term=payload.term,
        term_start_date=payload.term_start_date, term_end_date=payload.term_end_date,
        day_of_week=payload.day_of_week, start_time=payload.start_time, end_time=payload.end_time,
        room=payload.room, session_type=payload.session_type,
    )
    db.add(entry)
    await record_audit_event(db, actor_id=user.id, action="timetable.create", resource_type="timetable_entry")
    await db.commit()
    await db.refresh(entry)
    return await _to_out(db, entry)


@router.get("", response_model=list[TimetableEntryOut])
async def list_entries(
    course_id: uuid.UUID | None = Query(None),
    term: str | None = Query(None),
    instructor_id: uuid.UUID | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TimetableEntry)
    if course_id:
        stmt = stmt.where(TimetableEntry.course_id == course_id)
    if term:
        stmt = stmt.where(TimetableEntry.term == term)
    if instructor_id:
        stmt = stmt.where(TimetableEntry.instructor_id == instructor_id)
    entries = (await db.execute(stmt.order_by(TimetableEntry.day_of_week, TimetableEntry.start_time))).scalars().all()
    return [await _to_out(db, e) for e in entries]


@router.patch("/{entry_id}", response_model=TimetableEntryOut)
async def update_entry(
    entry_id: uuid.UUID,
    payload: TimetableEntryUpdate,
    user: User = Depends(require_permission("timetable.manage")),
    db: AsyncSession = Depends(get_db),
):
    entry = await db.get(TimetableEntry, entry_id)
    if entry is None:
        raise NotFoundError("Timetable entry not found.")
    await _require_course_ownership(db, user, entry.course_id)

    updates = payload.model_dump(exclude_unset=True)
    merged = {
        "term": updates.get("term", entry.term),
        "day_of_week": updates.get("day_of_week", entry.day_of_week),
        "start_time": updates.get("start_time", entry.start_time),
        "end_time": updates.get("end_time", entry.end_time),
        "room": updates.get("room", entry.room),
    }
    if merged["end_time"] <= merged["start_time"]:
        raise ValidationAppError("end_time must be after start_time.")
    await check_conflict(
        db, instructor_id=entry.instructor_id, room=merged["room"], term=merged["term"],
        day_of_week=merged["day_of_week"], start_time=merged["start_time"], end_time=merged["end_time"],
        exclude_entry_id=entry_id,
    )
    for field, value in updates.items():
        setattr(entry, field, value)
    await db.commit()
    await db.refresh(entry)
    return await _to_out(db, entry)


@router.delete("/{entry_id}", response_model=MessageResponse)
async def delete_entry(
    entry_id: uuid.UUID,
    user: User = Depends(require_permission("timetable.manage")),
    db: AsyncSession = Depends(get_db),
):
    entry = await db.get(TimetableEntry, entry_id)
    if entry is None:
        raise NotFoundError("Timetable entry not found.")
    await _require_course_ownership(db, user, entry.course_id)
    await db.delete(entry)
    await record_audit_event(db, actor_id=user.id, action="timetable.delete", resource_type="timetable_entry", resource_id=str(entry_id))
    await db.commit()
    return MessageResponse(message="Timetable entry deleted.")


async def _my_course_ids(db: AsyncSession, user: User) -> list[uuid.UUID]:
    """Return all courses relevant to a user's personal timetable.

    Teaching and enrollment are independent relationships, so don't let a
    role/permission branch suppress the other relationship. This also makes
    the endpoint resilient when a user temporarily has multiple roles.
    """
    taught = (await db.execute(select(Course.id).where(Course.instructor_id == user.id))).scalars().all()
    enrolled = (await db.execute(
        select(Enrollment.course_id).where(Enrollment.student_id == user.id, Enrollment.status != "dropped")
    )).scalars().all()
    return list(dict.fromkeys([*taught, *enrolled]))


@router.get("/me", response_model=list[TimetableEntryOut])
async def my_timetable(
    term: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course_ids = await _my_course_ids(db, user)
    if not course_ids:
        return []
    stmt = select(TimetableEntry).where(TimetableEntry.course_id.in_(course_ids))
    if term:
        stmt = stmt.where(TimetableEntry.term == term)
    else:
        stmt = stmt.where(TimetableEntry.term_end_date >= date.today())
    entries = (await db.execute(stmt.order_by(TimetableEntry.day_of_week, TimetableEntry.start_time))).scalars().all()
    return [await _to_out(db, e) for e in entries]


@router.get("/me/export.ics")
async def export_my_timetable_ics(
    term: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course_ids = await _my_course_ids(db, user)
    entries: list[TimetableEntry] = []
    if course_ids:
        stmt = select(TimetableEntry).where(TimetableEntry.course_id.in_(course_ids))
        if term:
            stmt = stmt.where(TimetableEntry.term == term)
        else:
            stmt = stmt.where(TimetableEntry.term_end_date >= date.today())
        entries = list((await db.execute(stmt)).scalars().all())

    course_titles = {}
    for cid in {e.course_id for e in entries}:
        course = await db.get(Course, cid)
        if course:
            course_titles[cid] = course.title

    ics_text = generate_ics(entries, calendar_name=f"{user.full_name} — Survival School Timetable", course_titles=course_titles)
    return Response(
        content=ics_text,
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=timetable.ics"},
    )
