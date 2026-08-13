from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import check_db_health, get_db
from app.dependencies import require_permission
from app.models.assessment import ExamAttempt, QuizAttempt
from app.models.certificate import Certificate
from app.models.lms import Course, Enrollment
from app.models.system import AuditLog
from app.models.user import User
from app.redis_client import check_redis_health

router = APIRouter(prefix="/admin", tags=["admin"])


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
    redis: bool
    status: str


@router.get("/dashboard", response_model=AdminDashboardOut)
async def admin_dashboard(user: User = Depends(require_permission("analytics.view")), db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
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
async def audit_logs(limit: int = Query(50, le=200), user: User = Depends(require_permission("system.manage")), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit))
    rows = result.scalars().all()
    return [AuditLogOut(
        id=str(r.id), actor_id=str(r.actor_id) if r.actor_id else None, action=r.action,
        resource_type=r.resource_type, resource_id=r.resource_id, result=r.result,
        created_at=r.created_at.isoformat(),
    ) for r in rows]


@router.get("/system-health", response_model=SystemHealthOut)
async def system_health(user: User = Depends(require_permission("system.manage"))):
    db_ok = await check_db_health()
    redis_ok = await check_redis_health()
    return SystemHealthOut(database=db_ok, redis=redis_ok, status="ok" if (db_ok and redis_ok) else "degraded")
