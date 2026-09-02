from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.db_utils import escape_like
from app.core.exceptions import ServiceUnavailableError, ValidationAppError
from app.database import get_db
from app.dependencies import get_current_user, get_current_verified_user, require_permission
from app.models.campus_timetable import (
    CampusTimetableEntry,
    CampusTimetableSource,
    PersonalTimetableEntry,
)
from app.models.user import Profile, User
from app.schemas.auth import MessageResponse
from app.schemas.campus_timetable import (
    CampusElectiveOut,
    CampusElectiveSectionOut,
    CampusImportErrorRow,
    CampusSectionOut,
    CampusSyncResultOut,
    CampusTeacherOut,
    CampusTimetableEntryOut,
    CampusTimetableSourceOut,
    LiveSyncConfigureIn,
    PersonalTimetableEntryOut,
    PersonalUploadResultOut,
)
from app.services.ai_provider import get_ai_provider
from app.services.audit_service import record_audit_event
from app.services.campus_timetable_service import (
    UnsafeUrlError,
    apply_campus_rows,
    fetch_and_apply_live_sync,
    parse_campus_rows_async,
)
from app.services.personal_timetable_service import (
    parse_personal_rows_async,
    replace_personal_timetable,
)
from app.services.rate_limit_service import enforce_rate_limit

router = APIRouter(prefix="/timetable/campus", tags=["campus-timetable"])
# A student's own upload lives under /timetable/me, not /timetable/campus —
# it's a different concept (personal, single-owner) from the shared campus
# feed above, and mixing them under one prefix would blur that distinction
# in the URL itself.
personal_router = APIRouter(prefix="/timetable/me", tags=["personal-timetable"])
settings = get_settings()


async def _get_or_create_source(db: AsyncSession) -> CampusTimetableSource:
    source = (await db.execute(select(CampusTimetableSource).where(CampusTimetableSource.singleton.is_(True)))).scalar_one_or_none()
    if source is None:
        source = CampusTimetableSource()
        db.add(source)
        await db.flush()
    return source


def _to_sync_result_out(result, error: str | None = None) -> CampusSyncResultOut:
    return CampusSyncResultOut(
        total_rows=result.total_rows,
        error_rows=[CampusImportErrorRow(**r) for r in result.error_rows],
        created=result.created, updated=result.updated, cancelled=result.cancelled,
        unchanged=result.unchanged, change_count=len(result.changes),
    )


@router.get("", response_model=list[CampusTimetableEntryOut])
async def list_campus_entries(
    section: str | None = Query(None),
    teacher: str | None = Query(None),
    course_name: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    include_cancelled: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CampusTimetableEntry)
    if section:
        stmt = stmt.where(CampusTimetableEntry.section.ilike(escape_like(section)))
    if teacher:
        stmt = stmt.where(CampusTimetableEntry.teacher_name.ilike(escape_like(teacher)))
    if course_name:
        # An elective's section numbering is scoped to that elective, not
        # the student's base section (see CampusElectiveOut/list_campus_electives)
        # — course_name + section together are what the frontend's elective
        # sub-section picker needs to fetch just that one elective group.
        stmt = stmt.where(CampusTimetableEntry.course_name.ilike(escape_like(course_name)))
    if date_from:
        stmt = stmt.where(CampusTimetableEntry.class_date >= date_from)
    if date_to:
        stmt = stmt.where(CampusTimetableEntry.class_date <= date_to)
    if not include_cancelled:
        stmt = stmt.where(CampusTimetableEntry.is_cancelled.is_(False))
    stmt = stmt.order_by(CampusTimetableEntry.class_date, CampusTimetableEntry.start_time).limit(1000)
    return (await db.execute(stmt)).scalars().all()


@router.get("/me", response_model=list[CampusTimetableEntryOut])
async def my_campus_entries(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = (await db.execute(select(Profile).where(Profile.user_id == user.id))).scalar_one_or_none()
    if profile is None or not profile.section:
        raise ValidationAppError("Set your section in your profile first (PATCH /users/me/profile) to see your personal schedule.")
    stmt = select(CampusTimetableEntry).where(
        CampusTimetableEntry.section.ilike(escape_like(profile.section)), CampusTimetableEntry.is_cancelled.is_(False)
    )
    # school disambiguates section numbers that repeat across schools (see
    # CampusSectionOut) — only applied when the student actually set one,
    # so an account that predates this field keeps matching on section
    # alone rather than suddenly seeing nothing.
    if profile.school:
        stmt = stmt.where(CampusTimetableEntry.school.ilike(escape_like(profile.school)))
    if date_from:
        stmt = stmt.where(CampusTimetableEntry.class_date >= date_from)
    else:
        stmt = stmt.where(CampusTimetableEntry.class_date >= date.today())
    if date_to:
        stmt = stmt.where(CampusTimetableEntry.class_date <= date_to)
    stmt = stmt.order_by(CampusTimetableEntry.class_date, CampusTimetableEntry.start_time).limit(500)
    return (await db.execute(stmt)).scalars().all()


@router.get("/sections", response_model=list[CampusSectionOut])
async def list_campus_sections(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Every real (school, year, section) combination currently in the
    timetable, so the frontend can offer a dropdown instead of a student
    typing a section name blind. Any signed-in user can read this — it's
    the same information already visible via the timetable itself, just
    aggregated for picking rather than displaying."""
    rows = (await db.execute(
        select(
            CampusTimetableEntry.school, CampusTimetableEntry.year_of_study,
            CampusTimetableEntry.section, CampusTimetableEntry.lab_group,
        ).where(CampusTimetableEntry.is_cancelled.is_(False)).distinct()
    )).all()
    grouped: dict[tuple[str | None, str | None, str], set[str]] = {}
    for school, year_of_study, section, lab_group in rows:
        key = (school, year_of_study, section)
        grouped.setdefault(key, set())
        if lab_group:
            grouped[key].add(lab_group)
    return [
        CampusSectionOut(school=school, year_of_study=year_of_study, section=section, lab_groups=sorted(labs))
        for (school, year_of_study, section), labs in sorted(
            grouped.items(), key=lambda kv: (kv[0][0] or "", kv[0][1] or "", kv[0][2])
        )
    ]


# Every teacher/free-rooms view below is "this week's pattern," not a
# literal date range — classes recur weekly for months (see
# campus_timetable_service._GRID_WEEKS_AHEAD), so a 7-day window from
# today catches exactly one real occurrence of every weekday's slot
# without the caller needing to know or care about that expansion.
_WEEK_WINDOW_DAYS = 7


@router.get("/teachers", response_model=list[CampusTeacherOut])
async def list_campus_teachers(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Every teacher with at least one class in the next 7 days, with a
    weekly class/day count (see CampusTeacherOut) — the search list behind
    the Teacher Timetable view. A specific teacher's own schedule reuses
    GET /timetable/campus?teacher=<name>&date_from=...&date_to=... rather
    than a second, parallel endpoint."""
    today = date.today()
    window_end = today + timedelta(days=_WEEK_WINDOW_DAYS)
    rows = (await db.execute(
        select(CampusTimetableEntry.teacher_name, func.count(), func.count(func.distinct(CampusTimetableEntry.day_of_week)))
        .where(
            CampusTimetableEntry.teacher_name.is_not(None), CampusTimetableEntry.is_cancelled.is_(False),
            CampusTimetableEntry.class_date >= today, CampusTimetableEntry.class_date < window_end,
        )
        .group_by(CampusTimetableEntry.teacher_name)
        .order_by(CampusTimetableEntry.teacher_name)
    )).all()
    return [CampusTeacherOut(teacher_name=name, class_count=count, day_count=days) for name, count, days in rows]


@router.get("/electives", response_model=list[CampusElectiveOut])
async def list_campus_electives(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Every elective course currently in the timetable with its distinct
    sections (each carrying whichever teacher is on record for it) — lets
    the frontend offer a per-elective section picker once a student
    checks that elective on, same shape the reference UI's "Emerging
    Tools Section" dropdown follows."""
    rows = (await db.execute(
        select(CampusTimetableEntry.course_name, CampusTimetableEntry.section, CampusTimetableEntry.teacher_name)
        .where(CampusTimetableEntry.is_elective.is_(True), CampusTimetableEntry.is_cancelled.is_(False))
        .distinct()
    )).all()
    grouped: dict[str, dict[str, str | None]] = {}
    for course_name, section, teacher_name in rows:
        grouped.setdefault(course_name, {})
        # A (course, section) combination should carry one teacher — if the
        # data genuinely disagrees across rows, keep whichever was seen
        # first rather than flip-flopping on dict iteration order.
        grouped[course_name].setdefault(section, teacher_name)
    return [
        CampusElectiveOut(course_name=course_name, sections=[
            CampusElectiveSectionOut(section=section, teacher_name=teacher_name)
            for section, teacher_name in sorted(sections.items())
        ])
        for course_name, sections in sorted(grouped.items())
    ]


@router.get("/free-rooms", response_model=list[str])
async def list_free_rooms(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Rooms with no class covering this exact instant right now — the
    whole timetable's room set minus whichever of them show up occupied
    today. A room that has simply never been used anywhere in the
    uploaded timetable isn't a "free room" in any useful sense, so the
    universe here is real known rooms, not a guess at every room the
    building might have. Naive server-local time, matching every other
    "today"/"now" in this file (class_date/start_time/end_time are
    themselves naive — the timetable feature has never been
    timezone-aware, see _parse_grid_rows' own date.today() in
    campus_timetable_service.py)."""
    now = datetime.now()
    all_rooms = (await db.execute(
        select(CampusTimetableEntry.room).where(CampusTimetableEntry.room.is_not(None)).distinct()
    )).scalars().all()
    occupied_rooms = (await db.execute(
        select(CampusTimetableEntry.room).where(
            CampusTimetableEntry.room.is_not(None), CampusTimetableEntry.is_cancelled.is_(False),
            CampusTimetableEntry.class_date == now.date(),
            CampusTimetableEntry.start_time <= now.time(), CampusTimetableEntry.end_time > now.time(),
        ).distinct()
    )).scalars().all()
    return sorted(set(all_rooms) - set(occupied_rooms))


@router.get("/source", response_model=CampusTimetableSourceOut)
async def get_source(
    user: User = Depends(require_permission("system.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await _get_or_create_source(db)


@router.post("/upload", response_model=CampusSyncResultOut)
async def upload_campus_timetable(
    file: UploadFile = File(...),
    user: User = Depends(require_permission("system.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Direct file upload path. Sets the source to 'upload' mode — if a live
    sync URL was previously configured, uploading a file doesn't disable it;
    the next scheduled poll still runs and will reconcile against whatever
    the sheet says (live_sync entries and upload entries are tracked
    separately by `source`, so they don't clobber each other).

    Gated by system.manage rather than the timetable.manage permission every
    instructor holds — this is one global feed for the whole campus, not a
    per-instructor course schedule, so any instructor being able to
    overwrite or soft-cancel every other instructor's rows would be a real
    privilege problem, not just an inconvenience."""
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValidationAppError(f"File exceeds the {settings.MAX_UPLOAD_MB}MB upload limit.")

    rows = await parse_campus_rows_async(file.filename or "", content)
    result = await apply_campus_rows(db, rows, source="upload")

    source = await _get_or_create_source(db)
    now = datetime.now(UTC)
    source.last_synced_at = now
    source.updated_by_id = user.id
    if result.error_rows:
        source.last_sync_status = "error"
        source.last_sync_error = f"{len(result.error_rows)} row(s) failed to parse — nothing was imported."
    else:
        source.last_sync_status = "ok"
        source.last_sync_error = None
        source.last_sync_row_count = result.total_rows

    await record_audit_event(
        db, actor_id=user.id, action="campus_timetable.uploaded", resource_type="campus_timetable_source",
        metadata={"created": result.created, "updated": result.updated, "cancelled": result.cancelled, "errors": len(result.error_rows)},
    )
    await db.commit()
    return _to_sync_result_out(result)


@router.put("/live-sync", response_model=CampusTimetableSourceOut)
async def configure_live_sync(
    payload: LiveSyncConfigureIn,
    user: User = Depends(require_permission("system.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Validates and stores the published-CSV URL, runs an immediate first
    sync so the admin gets feedback right away, then enables periodic
    polling (see scheduler_runtime.py's housekeeping tick)."""
    try:
        result = await fetch_and_apply_live_sync(db, payload.csv_url)
    except UnsafeUrlError:
        raise
    except Exception as e:
        raise ValidationAppError(f"Couldn't sync from that URL: {e}") from e

    source = await _get_or_create_source(db)
    source.mode = "live_sync"
    source.sheet_csv_url = payload.csv_url
    source.poll_interval_minutes = payload.poll_interval_minutes
    source.updated_by_id = user.id
    source.last_synced_at = datetime.now(UTC)
    source.last_sync_status = "error" if result.error_rows else "ok"
    source.last_sync_error = f"{len(result.error_rows)} row(s) failed to parse." if result.error_rows else None
    source.last_sync_row_count = result.total_rows

    await record_audit_event(
        db, actor_id=user.id, action="campus_timetable.live_sync_configured", resource_type="campus_timetable_source",
        metadata={"csv_url": payload.csv_url, "poll_interval_minutes": payload.poll_interval_minutes},
    )
    await db.commit()
    await db.refresh(source)
    return source


@router.delete("/live-sync", response_model=CampusTimetableSourceOut)
async def disable_live_sync(
    user: User = Depends(require_permission("system.manage")),
    db: AsyncSession = Depends(get_db),
):
    source = await _get_or_create_source(db)
    source.mode = "upload"
    source.sheet_csv_url = None
    source.updated_by_id = user.id
    await record_audit_event(db, actor_id=user.id, action="campus_timetable.live_sync_disabled", resource_type="campus_timetable_source")
    await db.commit()
    await db.refresh(source)
    return source


@personal_router.post("/upload", response_model=PersonalUploadResultOut)
async def upload_my_timetable(
    file: UploadFile = File(...),
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Any student can upload their own CSV/XLSX here — unlike
    /timetable/campus/upload, which is system.manage-gated because it
    writes into the one shared institution-wide feed, this only ever
    touches the uploader's own rows. Wholesale-replaces whatever they
    uploaded before. Accepts either a pre-filtered personal file (Course,
    Date, StartTime, EndTime, Room, Teacher, Elective) or the real
    institution-wide grid/lab spreadsheet — for the latter, every
    section's classes get parsed and then reduced to just this student's
    own via their profile section/school (see parse_personal_rows)."""
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValidationAppError(f"File exceeds the {settings.MAX_UPLOAD_MB}MB upload limit.")

    profile = (await db.execute(select(Profile).where(Profile.user_id == user.id))).scalar_one_or_none()
    rows = await parse_personal_rows_async(
        file.filename or "", content,
        section=profile.section if profile else None, school=profile.school if profile else None,
    )
    result = await replace_personal_timetable(db, user.id, rows)
    return PersonalUploadResultOut(
        total_rows=result.total_rows,
        error_rows=[CampusImportErrorRow(**r) for r in result.error_rows],
        imported=result.imported,
    )


@personal_router.get("/personal", response_model=list[PersonalTimetableEntryOut])
async def my_personal_timetable(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(PersonalTimetableEntry).where(PersonalTimetableEntry.user_id == user.id)
    if date_from:
        stmt = stmt.where(PersonalTimetableEntry.class_date >= date_from)
    else:
        stmt = stmt.where(PersonalTimetableEntry.class_date >= date.today())
    if date_to:
        stmt = stmt.where(PersonalTimetableEntry.class_date <= date_to)
    stmt = stmt.order_by(PersonalTimetableEntry.class_date, PersonalTimetableEntry.start_time).limit(500)
    return (await db.execute(stmt)).scalars().all()


@personal_router.delete("/personal", response_model=MessageResponse)
async def clear_my_personal_timetable(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Reverts to the section-filtered campus view (GET /timetable/campus/me)
    — lets a student undo an upload without waiting for a fresh one to
    overwrite it."""
    await db.execute(delete(PersonalTimetableEntry).where(PersonalTimetableEntry.user_id == user.id))
    await db.commit()
    return MessageResponse(message="Your uploaded timetable was cleared.")


class TimetableChatRequest(BaseModel):
    question: str


class TimetableChatResponse(BaseModel):
    answer: str
    provider: str


# How far ahead of today the chat's schedule context reaches — enough for
# "what's my Friday like" or "when's my next lab" without ballooning the
# prompt with months of recurring grid-format occurrences.
_CHAT_SCHEDULE_WINDOW_DAYS = 21

# Caps how many campus-wide rows get folded into the prompt alongside the
# student's own schedule (see _campus_wide_busy_text below) — a genuinely
# large institution's full 21-day campus feed could otherwise blow up the
# request. Most cross-entity questions ("when is Prof X free", "when are
# two sections both free") only need day/time granularity, so this is a
# generous cap in practice, not a real limitation.
_CAMPUS_WIDE_ROW_CAP = 3000

_TIMETABLE_CHAT_SYSTEM_PROMPT = (
    "You are a timetable assistant for a university student. Answer the student's question using ONLY the "
    "schedule data provided below — never invent or guess a class, time, room, or teacher that isn't listed "
    "there. If the question can't be answered from this data (e.g. it asks about a class, date, or detail not "
    "present, or a teacher/section that never appears below), say plainly that you don't have that information "
    "instead of making something up. Be concise.\n\n"
    "=== {source_label} ===\n{schedule_text}\n\n"
    "=== Everyone else's busy times, for questions about a specific teacher's availability or comparing free "
    "time across sections (day and time range only — ask about the student's own schedule above for room/course "
    "detail) ===\n{campus_wide_text}"
)


async def _campus_wide_busy_text(db: AsyncSession, today: date, window_end: date) -> str:
    """A compact, campus-wide busy-times listing — every teacher and every
    (school, section)'s occupied day/time slots in the window, without the
    student's-own-schedule level of detail (course name, room). This is
    what lets the assistant answer "when is Prof X free" or "when are
    SCDS 3 and SOAI 2 both free" — questions about someone OTHER than the
    asking student — without dumping the full campus timetable verbatim."""
    rows = (await db.execute(
        select(
            CampusTimetableEntry.teacher_name, CampusTimetableEntry.school, CampusTimetableEntry.section,
            CampusTimetableEntry.class_date, CampusTimetableEntry.start_time, CampusTimetableEntry.end_time,
        )
        .where(
            CampusTimetableEntry.is_cancelled.is_(False),
            CampusTimetableEntry.class_date >= today, CampusTimetableEntry.class_date <= window_end,
        )
        .order_by(CampusTimetableEntry.class_date, CampusTimetableEntry.start_time)
        .limit(_CAMPUS_WIDE_ROW_CAP)
    )).all()
    if not rows:
        return "(no campus-wide timetable data available)"

    by_teacher: dict[str, list[str]] = {}
    by_section: dict[str, list[str]] = {}
    for teacher_name, school, section, class_date, start_time, end_time in rows:
        slot = f"{class_date.isoformat()} ({class_date.strftime('%A')}) {start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}"
        if teacher_name:
            by_teacher.setdefault(teacher_name, []).append(slot)
        section_key = f"{school + ' ' if school else ''}Section {section}"
        by_section.setdefault(section_key, []).append(slot)

    lines = ["Teachers:"]
    for teacher_name, slots in sorted(by_teacher.items()):
        lines.append(f"- {teacher_name}: busy {'; '.join(slots)}")
    lines.append("\nSections:")
    for section_key, slots in sorted(by_section.items()):
        lines.append(f"- {section_key}: busy {'; '.join(slots)}")
    return "\n".join(lines)


@personal_router.post("/chat", response_model=TimetableChatResponse)
async def timetable_chat(
    payload: TimetableChatRequest,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Answers freeform questions about the student's own live schedule
    (their personal upload if they have one, same precedence the
    /timetable page itself uses, otherwise their section's campus feed),
    plus cross-entity questions like "when is Prof X free" or "when are
    two sections both free" via a compact campus-wide busy-times summary
    (see _campus_wide_busy_text). The AI only ever sees real parsed data
    in its system prompt, with an explicit instruction never to invent
    anything beyond it."""
    await enforce_rate_limit(f"timetable-chat:{user.id}", limit=20, window_seconds=3600)

    question = payload.question.strip()
    if not question:
        raise ValidationAppError("Ask a question first.")
    if len(question) > 500:
        raise ValidationAppError("That question is too long.")

    today = date.today()
    window_end = today + timedelta(days=_CHAT_SCHEDULE_WINDOW_DAYS)

    personal = (await db.execute(
        select(PersonalTimetableEntry)
        .where(
            PersonalTimetableEntry.user_id == user.id,
            PersonalTimetableEntry.class_date >= today,
            PersonalTimetableEntry.class_date <= window_end,
        )
        .order_by(PersonalTimetableEntry.class_date, PersonalTimetableEntry.start_time)
    )).scalars().all()

    if personal:
        entries: list = personal
        source_label = "the student's own uploaded personal schedule"
    else:
        profile = (await db.execute(select(Profile).where(Profile.user_id == user.id))).scalar_one_or_none()
        entries = []
        if profile is not None and profile.section:
            stmt = select(CampusTimetableEntry).where(
                CampusTimetableEntry.section.ilike(escape_like(profile.section)),
                CampusTimetableEntry.is_cancelled.is_(False),
                CampusTimetableEntry.class_date >= today,
                CampusTimetableEntry.class_date <= window_end,
            )
            if profile.school:
                stmt = stmt.where(CampusTimetableEntry.school.ilike(escape_like(profile.school)))
            stmt = stmt.order_by(CampusTimetableEntry.class_date, CampusTimetableEntry.start_time)
            entries = (await db.execute(stmt)).scalars().all()
        source_label = "the student's section's campus schedule"

    if not entries:
        return TimetableChatResponse(
            answer="I don't have any schedule data for you yet — upload your own timetable or set your section on the timetable page first.",
            provider="none",
        )

    schedule_text = "\n".join(
        f"{e.class_date.isoformat()} ({e.class_date.strftime('%A')}) "
        f"{e.start_time.strftime('%H:%M')}-{e.end_time.strftime('%H:%M')} {e.course_name} — "
        f"room {e.room or 'TBD'}{f', {e.teacher_name}' if e.teacher_name else ''}"
        for e in entries
    )
    campus_wide_text = await _campus_wide_busy_text(db, today, window_end)

    provider = get_ai_provider()
    response = await provider.chat(
        [{"role": "user", "content": question}],
        system_prompt=_TIMETABLE_CHAT_SYSTEM_PROMPT.format(
            source_label=source_label, schedule_text=schedule_text, campus_wide_text=campus_wide_text,
        ),
    )
    if response.error or not response.content:
        raise ServiceUnavailableError("The timetable assistant is unavailable right now. Please try again.")

    return TimetableChatResponse(answer=response.content, provider=response.provider)
