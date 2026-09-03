from __future__ import annotations

import hmac
import time
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.runtime import PROCESS_STARTED_AT
from app.database import check_db_health, get_db
from app.dependencies import require_permission
from app.models.contest import ContestAttempt, ContestCertificate
from app.models.system import AuditLog
from app.models.user import InstructorApplication, Role, User
from app.redis_client import check_redis_health
from app.schemas.auth import InstructorApplicationOut, InstructorApplicationReview, UserOut
from app.services.audit_service import record_audit_event
from app.services.cache_service import cache_get_json, cache_set_json
from app.services.n8n_service import emit_event
from app.services.powerbi_service import sync_daily_engagement

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()


class AdminDashboardOut(BaseModel):
    total_students: int
    active_students_7d: int
    certificates_issued: int
    contest_attempts_30d: int


class AuditLogOut(BaseModel):
    id: str
    actor_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    result: str
    created_at: str


class SystemHealthOut(BaseModel):
    database: bool
    database_latency_ms: float | None
    redis: bool
    redis_latency_ms: float | None
    status: str
    app_version: str
    environment: str
    uptime_seconds: float


@router.get("/dashboard", response_model=AdminDashboardOut)
async def admin_dashboard(user: User = Depends(require_permission("analytics.view")), db: AsyncSession = Depends(get_db)):
    now = datetime.now(UTC)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    total_students = (await db.execute(select(func.count(User.id)).where(User.deleted_at.is_(None)))).scalar_one()
    active_7d = (await db.execute(
        select(func.count(func.distinct(User.id))).where(User.last_login_at >= week_ago, User.deleted_at.is_(None))
    )).scalar_one()
    certs = (await db.execute(select(func.count(ContestCertificate.id)))).scalar_one()
    contest_attempts = (await db.execute(select(func.count(ContestAttempt.id)).where(ContestAttempt.created_at >= month_ago))).scalar_one()

    return AdminDashboardOut(
        total_students=total_students, active_students_7d=active_7d,
        certificates_issued=certs, contest_attempts_30d=contest_attempts,
    )


@router.get("/audit-logs", response_model=list[AuditLogOut])
async def audit_logs(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    actor_id: uuid.UUID | None = Query(None),
    action: str | None = Query(None, description="Exact match, e.g. 'certificate.revoke'"),
    resource_type: str | None = Query(None),
    result: str | None = Query(None, pattern=r"^(success|failure)$"),
    since: datetime | None = Query(None, description="ISO 8601 — only logs at/after this time"),
    until: datetime | None = Query(None, description="ISO 8601 — only logs at/before this time"),
    user: User = Depends(require_permission("system.manage")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AuditLog)
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type is not None:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if result is not None:
        stmt = stmt.where(AuditLog.result == result)
    if since is not None:
        stmt = stmt.where(AuditLog.created_at >= since)
    if until is not None:
        stmt = stmt.where(AuditLog.created_at <= until)

    result_rows = await db.execute(stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset))
    rows = result_rows.scalars().all()
    return [AuditLogOut(
        id=str(r.id), actor_id=str(r.actor_id) if r.actor_id else None, action=r.action,
        resource_type=r.resource_type, resource_id=r.resource_id, result=r.result,
        created_at=r.created_at.isoformat(),
    ) for r in rows]


_SYSTEM_HEALTH_CACHE_TTL = 3


@router.get("/system-health", response_model=SystemHealthOut)
async def system_health(user: User = Depends(require_permission("system.manage"))):
    # Each call does a real DB round trip plus a real Redis PING — fine for
    # one admin loading the dashboard, but several admins hitting it around
    # the same moment (e.g. everyone checking in at the start of an exam
    # window) turns into that many concurrent live health probes. A few
    # seconds of staleness is a non-issue for a status dashboard, so cache
    # the result briefly instead of re-probing on every request.
    cached = await cache_get_json("admin:system-health")
    if cached is not None:
        return SystemHealthOut(**cached)

    db_start = time.perf_counter()
    db_ok = await check_db_health()
    db_latency_ms = round((time.perf_counter() - db_start) * 1000, 2) if db_ok else None

    redis_start = time.perf_counter()
    redis_ok = await check_redis_health()
    redis_latency_ms = round((time.perf_counter() - redis_start) * 1000, 2) if redis_ok else None

    result = SystemHealthOut(
        database=db_ok, database_latency_ms=db_latency_ms,
        redis=redis_ok, redis_latency_ms=redis_latency_ms,
        status="ok" if (db_ok and redis_ok) else "degraded",
        app_version=settings.SERVICE_VERSION, environment=settings.APP_ENV,
        uptime_seconds=round(time.time() - PROCESS_STARTED_AT, 1),
    )
    await cache_set_json("admin:system-health", result.model_dump(mode="json"), _SYSTEM_HEALTH_CACHE_TTL)
    return result


@router.get("/users", response_model=list[UserOut])
async def admin_list_users(
    q: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("users.read")),
    db: AsyncSession = Depends(get_db),
):
    """Same query as GET /users — kept here too under /admin because that's
    where the admin frontend (and the production audit) expects it."""
    stmt = select(User).options(selectinload(User.roles)).where(User.deleted_at.is_(None))
    if q:
        stmt = stmt.where(User.email.ilike(f"%{q}%") | User.full_name.ilike(f"%{q}%"))
    result = await db.execute(stmt.order_by(User.created_at.desc()).limit(limit).offset(offset))
    users = result.scalars().all()
    return [UserOut(id=u.id, email=u.email, full_name=u.full_name, is_email_verified=u.is_email_verified,
                     is_active=u.is_active, roles=[r.name for r in u.roles]) for u in users]


@router.post("/users/{user_id}/deactivate", response_model=UserOut)
async def deactivate_user(
    user_id: uuid.UUID,
    admin: User = Depends(require_permission("users.update")),
    db: AsyncSession = Depends(get_db),
):
    target = (await db.execute(select(User).where(User.id == user_id).options(selectinload(User.roles)))).scalar_one_or_none()
    if target is None:
        raise NotFoundError("User not found.")
    target.is_active = False
    await record_audit_event(db, actor_id=admin.id, action="user.deactivated", resource_type="user", resource_id=str(user_id))
    await db.commit()
    return UserOut(id=target.id, email=target.email, full_name=target.full_name,
                    is_email_verified=target.is_email_verified, is_active=target.is_active,
                    roles=[r.name for r in target.roles])


@router.post("/users/{user_id}/activate", response_model=UserOut)
async def activate_user(
    user_id: uuid.UUID,
    admin: User = Depends(require_permission("users.update")),
    db: AsyncSession = Depends(get_db),
):
    target = (await db.execute(select(User).where(User.id == user_id).options(selectinload(User.roles)))).scalar_one_or_none()
    if target is None:
        raise NotFoundError("User not found.")
    target.is_active = True
    await record_audit_event(db, actor_id=admin.id, action="user.activated", resource_type="user", resource_id=str(user_id))
    await db.commit()
    return UserOut(id=target.id, email=target.email, full_name=target.full_name,
                    is_email_verified=target.is_email_verified, is_active=target.is_active,
                    roles=[r.name for r in target.roles])


class PowerBISyncOut(BaseModel):
    status: str
    reason: str | None = None
    date: str | None = None


@router.post("/powerbi/sync", response_model=PowerBISyncOut)
async def trigger_powerbi_sync(
    admin: User = Depends(require_permission("analytics.view")),
    db: AsyncSession = Depends(get_db),
):
    """Manual on-demand trigger for the daily Power BI aggregate-analytics
    push (same code path as the worker's scheduled job — see
    app/workers/worker.py::run_powerbi_sync) so an admin can test/verify the
    integration without waiting for the next scheduled run. Returns
    status=skipped (not an error) if POWERBI_* env vars aren't configured."""
    result = await sync_daily_engagement(db)
    await record_audit_event(
        db, actor_id=admin.id, action="powerbi.sync_triggered",
        resource_type="powerbi_dataset", resource_id=result.get("date"),
        metadata={"status": result["status"]},
    )
    await db.commit()
    return PowerBISyncOut(status=result["status"], reason=result.get("reason"), date=result.get("date"))


class MaintenanceResetOut(BaseModel):
    status: str
    detail: str


@router.post("/maintenance/reset-accounts", response_model=MaintenanceResetOut)
async def maintenance_reset_accounts(
    db: AsyncSession = Depends(get_db),
    x_maintenance_secret: str | None = Header(default=None),
):
    """Destructive, explicitly-gated maintenance escape hatch: deletes every
    user account and everything that owns a hard reference to one (sessions,
    tokens, enrollments, submissions, etc. — every FK declared CASCADE),
    while leaving shared platform content intact where its FK is declared
    SET NULL (a contest's created_by, a chat room's created_by, a file's
    owner_id, ...) exactly as those models were designed to behave on a
    single user's deletion.

    Uses a plain DELETE, not TRUNCATE ... CASCADE — Postgres's TRUNCATE
    CASCADE does not respect each dependent table's own ON DELETE action at
    all; it unconditionally empties every table with any FK back to the
    truncated one, SET NULL included. That silently turned "reset accounts"
    into "also wipe every contest, chat room, and uploaded file on the
    platform," which nothing about this endpoint's own name or its own
    audience (school-wide account reset) implies.

    Deliberately NOT behind require_permission()/a user JWT — the whole
    point is to be usable even when there are zero working accounts left,
    or when the only credential available is this one-time secret. Instead
    it's gated by MAINTENANCE_SECRET, which is unset by default (None), so
    this endpoint 404s unless an operator has deliberately opted in by
    setting that env var — and it's meant to be unset again immediately
    after use. Exists because Render's free tier doesn't always offer easy
    interactive shell access; this is the practical alternative for running
    a real destructive maintenance operation against production.
    """
    if not settings.MAINTENANCE_SECRET:
        raise NotFoundError("Not found.")
    # V-04: Use constant-time comparison to prevent timing attacks on the
    # maintenance secret.
    if not x_maintenance_secret or not hmac.compare_digest(x_maintenance_secret, settings.MAINTENANCE_SECRET):
        raise NotFoundError("Not found.")

    result = await db.execute(text("DELETE FROM users"))
    # No actor_id — this bypasses normal auth entirely (see docstring), so
    # there is no user to attribute the action to. Still worth a row: the
    # request itself (and that the secret check passed) is the fact worth
    # recording, distinct from every other audit entry which has an actor.
    await record_audit_event(
        db, actor_id=None, action="maintenance.reset_accounts", resource_type="user", resource_id="*",
        metadata={"deleted_count": result.rowcount},
    )
    await db.commit()

    return MaintenanceResetOut(
        status="ok",
        detail=f"Deleted {result.rowcount} user account(s) and everything owned by them. Shared content (contests, chat rooms, files, etc.) had its creator/owner reference cleared but was not deleted. Roles/permissions/badges were left intact.",
    )


def _application_out(app_row: InstructorApplication) -> InstructorApplicationOut:
    return InstructorApplicationOut(
        id=app_row.id, user_id=app_row.user_id, applicant_email=app_row.user.email,
        applicant_name=app_row.user.full_name, institution=app_row.institution, reason=app_row.reason,
        status=app_row.status, created_at=app_row.created_at, reviewed_at=app_row.reviewed_at,
        review_note=app_row.review_note,
    )


@router.get("/instructor-applications", response_model=list[InstructorApplicationOut])
async def list_instructor_applications(
    status_filter: str = Query(default="pending", alias="status", pattern="^(pending|approved|rejected|all)$"),
    admin: User = Depends(require_permission("users.update")),
    db: AsyncSession = Depends(get_db),
):
    query = select(InstructorApplication).options(selectinload(InstructorApplication.user)).order_by(
        InstructorApplication.created_at.desc()
    )
    if status_filter != "all":
        query = query.where(InstructorApplication.status == status_filter)
    rows = (await db.execute(query)).scalars().all()
    return [_application_out(a) for a in rows]


@router.post("/instructor-applications/{application_id}/approve", response_model=InstructorApplicationOut)
async def approve_instructor_application(
    application_id: uuid.UUID,
    payload: InstructorApplicationReview,
    admin: User = Depends(require_permission("users.update")),
    db: AsyncSession = Depends(get_db),
):
    """Approving grants INSTRUCTOR through the same path as
    POST /users/{id}/roles/{role} — this endpoint never appends the role
    itself without going through that audited, reviewed transition."""
    application = (await db.execute(
        select(InstructorApplication)
        .where(InstructorApplication.id == application_id)
        .options(selectinload(InstructorApplication.user).selectinload(User.roles))
    )).scalar_one_or_none()
    if application is None:
        raise NotFoundError("Instructor application not found.")
    if application.status != "pending":
        raise ConflictError(f"This application was already {application.status}.")

    instructor_role = (await db.execute(select(Role).where(Role.name == "INSTRUCTOR"))).scalar_one_or_none()
    if instructor_role is None:
        raise NotFoundError("INSTRUCTOR role is not seeded. Run database seed script.")
    if instructor_role not in application.user.roles:
        application.user.roles.append(instructor_role)

    application.status = "approved"
    application.reviewed_by_id = admin.id
    application.reviewed_at = datetime.now(UTC)
    application.review_note = payload.note

    await record_audit_event(
        db, actor_id=admin.id, action="instructor_application.approved", resource_type="instructor_application",
        resource_id=str(application.id), metadata={"applicant_user_id": str(application.user_id)},
    )
    await db.commit()
    await db.refresh(application)

    await emit_event(
        "instructor.application_approved",
        {"email": application.user.email, "full_name": application.user.full_name},
    )

    return _application_out(application)


@router.post("/instructor-applications/{application_id}/reject", response_model=InstructorApplicationOut)
async def reject_instructor_application(
    application_id: uuid.UUID,
    payload: InstructorApplicationReview,
    admin: User = Depends(require_permission("users.update")),
    db: AsyncSession = Depends(get_db),
):
    application = (await db.execute(
        select(InstructorApplication)
        .where(InstructorApplication.id == application_id)
        .options(selectinload(InstructorApplication.user))
    )).scalar_one_or_none()
    if application is None:
        raise NotFoundError("Instructor application not found.")
    if application.status != "pending":
        raise ConflictError(f"This application was already {application.status}.")

    application.status = "rejected"
    application.reviewed_by_id = admin.id
    application.reviewed_at = datetime.now(UTC)
    application.review_note = payload.note

    await record_audit_event(
        db, actor_id=admin.id, action="instructor_application.rejected", resource_type="instructor_application",
        resource_id=str(application.id), metadata={"applicant_user_id": str(application.user_id)},
    )
    await db.commit()
    await db.refresh(application)

    return _application_out(application)
