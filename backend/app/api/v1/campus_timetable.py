from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.db_utils import escape_like
from app.core.exceptions import ValidationAppError
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
    CampusImportErrorRow,
    CampusSectionOut,
    CampusSyncResultOut,
    CampusTimetableEntryOut,
    CampusTimetableSourceOut,
    LiveSyncConfigureIn,
    PersonalTimetableEntryOut,
    PersonalUploadResultOut,
)
from app.services.audit_service import record_audit_event
from app.services.campus_timetable_service import (
    UnsafeUrlError,
    apply_campus_rows,
    fetch_and_apply_live_sync,
    parse_campus_rows,
)
from app.services.personal_timetable_service import parse_personal_rows, replace_personal_timetable

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
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    include_cancelled: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CampusTimetableEntry)
    if section:
        stmt = stmt.where(CampusTimetableEntry.section.ilike(escape_like(section)))
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

    rows = parse_campus_rows(file.filename or "", content)
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
    uploaded before, same shape/columns as the campus importer (Course,
    Date, StartTime, EndTime, Room, Teacher, Elective — School/Section/
    LabGroup/Year are irrelevant here since it's already scoped to one
    person)."""
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValidationAppError(f"File exceeds the {settings.MAX_UPLOAD_MB}MB upload limit.")

    rows = parse_personal_rows(file.filename or "", content)
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
