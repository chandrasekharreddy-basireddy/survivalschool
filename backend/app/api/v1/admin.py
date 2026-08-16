from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.exceptions import NotFoundError
from app.core.runtime import PROCESS_STARTED_AT
from app.database import check_db_health, get_db
from app.dependencies import require_permission
from app.models.assessment import ExamAttempt, QuizAttempt
from app.models.certificate import Certificate
from app.models.lms import Course, Enrollment
from app.models.system import AuditLog
from app.models.user import User
from app.redis_client import check_redis_health
from app.schemas.auth import UserOut
from app.services.audit_service import record_audit_event
from app.services.powerbi_service import sync_daily_engagement

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()


class AdminDashboardOut(BaseModel):
    total_students: int
    active_students_7d: int
    total_courses: int
    published_courses: int
    total_enrollments: int
    certificates_issued: int
    quiz_attempts_30d: int
    exam_attempts_30d: int


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
    active_7d = (await db.execute(select(func.count(func.distinct(User.id))).where(User.last_login_at >= week_ago))).scalar_one()
    total_courses = (await db.execute(select(func.count(Course.id)).where(Course.deleted_at.is_(None)))).scalar_one()
    published = (await db.execute(select(func.count(Course.id)).where(Course.is_published.is_(True)))).scalar_one()
    enrollments = (await db.execute(select(func.count(Enrollment.id)))).scalar_one()
    certs = (await db.execute(select(func.count(Certificate.id)))).scalar_one()
    quiz_attempts = (await db.execute(select(func.count(QuizAttempt.id)).where(QuizAttempt.created_at >= month_ago))).scalar_one()
    exam_attempts = (await db.execute(select(func.count(ExamAttempt.id)).where(ExamAttempt.created_at >= month_ago))).scalar_one()

    return AdminDashboardOut(
        total_students=total_students, active_students_7d=active_7d, total_courses=total_courses,
        published_courses=published, total_enrollments=enrollments, certificates_issued=certs,
        quiz_attempts_30d=quiz_attempts, exam_attempts_30d=exam_attempts,
    )


@router.get("/audit-logs", response_model=list[AuditLogOut])
async def audit_logs(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    actor_id: uuid.UUID | None = Query(None),
    action: str | None = Query(None, description="Exact match, e.g. 'certificate.revoke'"),
    resource_type: str | None = Query(None),
    result: str | None = Query(None, pattern=r"^(success|failure)$"),
    since: datetime | None = Query(None, description="ISO 8601 â€” only logs at/after this time"),
    until: datetime | None = Query(None, description="ISO 8601 â€” only logs at/before this time"),
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


@router.get("/system-health", response_model=SystemHealthOut)
async def system_health(user: User = Depends(require_permission("system.manage"))):
    db_start = time.perf_counter()
    db_ok = await check_db_health()
    db_latency_ms = round((time.perf_counter() - db_start) * 1000, 2) if db_ok else None

    redis_start = time.perf_counter()
    redis_ok = await check_redis_health()
    redis_latency_ms = round((time.perf_counter() - redis_start) * 1000, 2) if redis_ok else None

    return SystemHealthOut(
        database=db_ok, database_latency_ms=db_latency_ms,
        redis=redis_ok, redis_latency_ms=redis_latency_ms,
        status="ok" if (db_ok and redis_ok) else "degraded",
        app_version=settings.SERVICE_VERSION, environment=settings.APP_ENV,
        uptime_seconds=round(time.time() - PROCESS_STARTED_AT, 1),
    )


@router.get("/users", response_model=list[UserOut])
async def admin_list_users(
    q: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("users.read")),
    db: AsyncSession = Depends(get_db),
):
    """Same query as GET /users â€” kept here too under /admin because that's
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
    push (same code path as the worker's scheduled job â€” see
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
    db: AsyncSession = Depends(Ãâ€¢Ã‘}â€˜Ë†Â¤Â°(â‚¬â‚¬â‚¬ÂÃ¡}Âµâ€¦Â¥Â¹Ã‘â€¢Â¹â€¦Â¹Ââ€¢}Ãâ€¢ÂÃ‰â€¢ÃÃ¨ÂÃÃ‘ÃˆÂÃ°Â9Â½Â¹â€â‚¬Ã´Â!â€¢â€¦â€˜â€¢ÃˆÂ¡â€˜â€¢â„¢â€¦Ã•Â±ÃÃµ9Â½Â¹â€Â¤Â°(Â¤Ã¨(â‚¬â‚¬â‚¬â‚¬Ë†Ë†â€°â€¢ÃÃ‘Ã‰Ã•ÂÃ‘Â¥Ã™â€Â°Ââ€¢Ã¡ÃÂ±Â¥ÂÂ¥Ã‘Â±Ã¤ÂµÂâ€¦Ã‘â€¢ÂÂÂµâ€¦Â¥Â¹Ã‘â€¢Â¹â€¦Â¹Ââ€Ââ€¢ÃÃâ€¦Ãâ€ÂÂ¡â€¦Ã‘ÂÂ Ã¨Ââ€˜â€¢Â±â€¢Ã‘â€¢ÃŒÂâ€¢Ã™â€¢Ã‰Ã¤(â‚¬â‚¬â‚¬ÂÃ•Ãâ€¢ÃˆÂâ€¦ÂÂÂ½Ã•Â¹Ãâ‚¬Â¡â€¦Â¹ÂÂâ€¢Ã™â€¢Ã‰Ã¥Ã‘Â¡Â¥Â¹Å“ÂÃ‘Â¡â€¦ÃÂÃ‰â€¢â„¢â€¢Ã‰â€¢Â¹Ââ€¢ÃŒÂÂ½Â¹â€ÂÃ™Â¥â€žÂâ€žÂÃ‰â€¢â€¦Â°Ââ„¢Â½Ã‰â€¢Â¥ÂÂ¸(â‚¬â‚¬â‚¬ÂÂ­â€¢Ã¤â‚¬Â´Â´ÂÃâ€¢ÃÃÂ¥Â½Â¹ÃŒÂ°ÂÃ‘Â½Â­â€¢Â¹ÃŒÂ°Ââ€¢Â¹Ã‰Â½Â±Â±Âµâ€¢Â¹Ã‘ÃŒÂ°ÂÃÃ•â€°ÂµÂ¥ÃÃÂ¥Â½Â¹ÃŒÂ°Ââ€¢Ã‘Å’Â¸Â¤ÂÃ™Â¥â€žÂÃ‘Â¡â€ÂÃâ€¦Âµâ€(â‚¬â‚¬â‚¬ÂQIU9Q€¸¸¸M…ÌÍÉ¥ÁÑÌ½É•Í•Ñ}…±±}…½Õ¹ÑÌ¹Áä¸((€€€•±¥‰•É…Ñ•±ä9=P‰•¡¥¹É•ÅÕ¥É•}Á•Éµ¥ÍÍ¥½¸ ¤½„ÕÍ•È)]P€´´Ñ¡”Ý¡½±”(€€€Á½¥¹Ð¥ÌÑ¼‰”ÕÍ…‰±”•Ù•¸Ý¡•¸Ñ¡•É”…É”é•É¼Ý½É­¥¹œ…½Õ¹ÑÌ±•™Ð°(€€€½ÈÝ¡•¸Ñ¡”½¹±äÉ•‘•¹Ñ¥…°…Ù…¥±…‰±”¥ÌÑ¡¥Ì½¹”µÑ¥µ”Í•É•Ð¸%¹ÍÑ•…(€€€¥ÐÌ…Ñ•‰ä5%9Q99}MIP°Ý¡¥ ¥ÌÕ¹Í•Ð‰ä‘•™…Õ±Ð€¡9½¹”¤°Í¼(€€€Ñ¡¥Ì•¹‘Á½¥¹Ð€ÐÀÑÌÕ¹±•ÍÌ…¸½Á•É…Ñ½È¡…Ì‘•±¥‰•É…Ñ•±ä½ÁÑ•¥¸‰ä(€€€Í•ÑÑ¥¹œÑ¡…Ð•¹ØÙ…È€´´…¹¥ÐÌµ•…¹ÐÑ¼‰”Õ¹Í•Ð……¥¸¥µµ•‘¥…Ñ•±ä(€€€…™Ñ•ÈÕÍ”¸á¥ÍÑÌ‰•…ÕÍ”I•¹‘•ÈÌ™É•”Ñ¥•È‘½•Í¸Ð…±Ý…åÌ½™™•È•…Íä(€€€¥¹Ñ•É…Ñ¥Ù”Í¡•±°…•ÍÌìÑ¡¥Ì¥ÌÑ¡”ÁÉ…Ñ¥…°…±Ñ•É¹…Ñ¥Ù”™½ÈÉÕ¹¹¥¹œ(€€€„É•…°‘•ÍÑÉÕÑ¥Ù”µ…¥¹Ñ•¹…¹”½Á•É…Ñ¥½¸……¥¹ÍÐÁÉ½‘ÕÑ¥½¸¸(€€€€ˆˆˆ(€€€¥˜¹½ÐÍ•ÑÑ¥¹Ì¹5%9Q99}MIPè(€€€€€€€É…¥Í”9½Ñ½Õ¹‘ÉÉ½È ‰9½Ð™½Õ¹¸ˆ¤(€€€¥˜¹½Ðá}µ…¥¹Ñ•¹…¹•}Í•É•Ð½Èá}µ…¥¹Ñ•¹…¹•}Í•É•Ð€„ôÍ•ÑÑ¥¹Ì¹5%9Q99}MIPè(€€€€€€€€ŒM…µ”€ÐÀÐ…Ì€‰Õ¹½¹™¥ÕÉ•ˆ€´´‘½¸ÐÉ•Ù•…°Ñ¡…ÐÑ¡¥Ì•¹‘Á½¥¹Ð(€€€€€€€€Œ•á¥ÍÑÌÑ¼„…±±•ÈÝ¡¼‘½•Í¸Ð…±É•…‘ä¡…Ù”Ñ¡”Í•É•Ð¸(€€€€€€€É…¥Í”9½Ñ½Õ¹‘ÉÉ½È ‰9½Ð™½Õ¹¸ˆ¤((€€€…Ý…¥Ð‘ˆ¹•á•ÕÑ”¡Ñ•áÐ ‰QIU9QQ	1ÕÍ•ÉÌIMQIP%9Q%QdMˆ¤¤(€€€…Ý…¥Ð‘ˆ¹½µµ¥Ð ¤((€€€É•ÑÕÉ¸5…¥¹Ñ•¹…¹•I•Í•Ñ=ÕÐ (€€€€€€€ÍÑ…ÑÕÌô‰½¬ˆ°(€€€€€€€‘•Ñ…¥°ô‰±°ÕÍ•È…½Õ¹ÑÌ€¡…¹•Ù•ÉåÑ¡¥¹œÉ•™•É•¹¥¹œÑ¡•´¤Ý•É”‘•±•Ñ•¸I½±•Ì½Á•Éµ¥ÍÍ¥½¹Ì½‰…‘•ÌÝ•É”±•™Ð¥¹Ñ…Ð¸ˆ°(€€€€¤(