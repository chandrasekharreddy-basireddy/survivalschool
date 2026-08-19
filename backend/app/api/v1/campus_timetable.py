from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import ValidationAppError
from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.campus_timetable import CampusTimetableEntry, CampusTimetableSource
from app.models.user import Profile, User
from app.schemas.campus_timetable import (
    CampusImportErrorRow,
    CampusSyncResultOut,
    CampusTimetableEntryOut,
    CampusTimetableSourceOut,
    LiveSyncConfigureIn,
)
from app.services.audit_service import record_audit_event
from app.services.campus_timetable_service import (
    UnsafeUrlError,
    apply_campus_rows,
    fetch_and_apply_live_sync,
    parse_campus_rows,
)

router = APIRouter(prefix="/timetable/campus", tags=["campus-timetable"])
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
        stmt = stmt.where(CampusTimetableEntry.section.ilike(section))
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
        CampusTimetableEntry.section.ilike(profile.section), CampusTimetableEntry.is_cancelled.is_(False)
    )
    if date_from:
        stmt = stmt.where(CampusTimetableEntry.class_date >= date_from)
    else:
        stmt = stmt.where(CampusTimetableEntry.class_date >= date.today())
    if date_to:
        stmt = stmt.where(CampusTimetableEntry.class_date <= date_to)
    stmt = stmt.order_by(CampusTimetableEntry.class_date, CampusTimetableEntry.start_time).limit(500)
    return (await db.execute(stmt)).scalars().all()


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
