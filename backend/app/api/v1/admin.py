from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone

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
async def audit_logs(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    actor_id: uuid.UUID | None = Query(None),
    action: str | None = Query(None, description="Exact match, e.g. 'certificate.revoke'"),
    resource_type: str | None = Query(None),
    result: str | None = Query(None, pattern=r"^(success|failure)$"),
    since: datetime | None = Query(None, description="ISO 8601 â€”Û›HÙÜÈ]ØY\ˆ\È[YHŠKˆ[[ˆ]][YH›Û™HH]Y\J›Û™K\ØÜš\[ÛH’TÓÈŒH8 %Û›HÙÜÈ]Ø™Y›Ü™H\È[YHŠKˆ\Ù\ˆ\Ù\ˆH\[™Ê™\]Z\™WÜ\›Z\ÜÚ[ÛŠœŞ\İ[K›X[˜YÙHŠJKˆˆ\Ş[˜ÔÙ\ÜÚ[ÛˆH\[™ÊÙ]ÙŠKŠN‚ˆİ]HÙ[Xİ
]Y]ÙÊBˆYˆXİÜ—ÚY\È›İ›Û™N‚ˆİ]Hİ]Ú\™J]Y]ÙË˜XİÜ—ÚYOHXİÜ—ÚY
BˆYˆXİ[Ûˆ\È›İ›Û™N‚ˆİ]Hİ]Ú\™J]Y]ÙË˜Xİ[ÛˆOHXİ[ÛŠBˆYˆ™\Ûİ\˜ÙWİ\H\È›İ›Û™N‚ˆİ]Hİ]Ú\™J]Y]ÙËœ™\Ûİ\˜ÙWİ\HOH™\Ûİ\˜ÙWİ\JBˆYˆ™\İ[\È›İ›Û™N‚ˆİ]Hİ]Ú\™J]Y]ÙËœ™\İ[OH™\İ[
BˆYˆÚ[˜ÙH\È›İ›Û™N‚ˆİ]Hİ]Ú\™J]Y]ÙË˜Ü™X]YØ]HÚ[˜ÙJBˆYˆ[[\È›İ›Û™N‚ˆİ]Hİ]Ú\™J]Y]ÙË˜Ü™X]YØ]H[[
B‚ˆ™\İ[Ü›İÜÈH]ØZ]‹™^Xİ]Jİ]›Ü™\—ØJ]Y]ÙË˜Ü™X]YØ]™\ØÊ
JK›[Z]
[Z]
K›Ù™œÙ]
Ù™œÙ]
JBˆ›İÜÈH™\İ[Ü›İÜËœØØ[\œÊ
K˜[

Bˆ™]\›ˆĞ]Y]ÙÓİ]
ˆY\İŠ‹šY
KXİÜ—ÚY\İŠ‹˜XİÜ—ÚY
HYˆ‹˜XİÜ—ÚY[ÙH›Û™KXİ[Û\‹˜Xİ[Û‹ˆ™\Ûİ\˜ÙWİ\O\‹œ™\Ûİ\˜ÙWİ\K™\Ûİ\˜ÙWÚY\‹œ™\Ûİ\˜ÙWÚY™\İ[\‹œ™\İ[ˆÜ™X]YØ]\‹˜Ü™X]YØ]š\ÛÙ›Ü›X]

Kˆ
H›Üˆˆ[ˆ›İÜ×B‚‚›İ]\‹™Ù]
‹ÜŞ\İ[KZX[‹™\ÜÛœÙWÛ[Ù[TŞ\İ[RX[İ]
B˜\Ş[˜ÈYˆŞ\İ[WÚX[
\Ù\ˆ\Ù\ˆH\[™Ê™\]Z\™WÜ\›Z\ÜÚ[ÛŠœŞ\İ[K›X[˜YÙHŠJJN‚ˆ—Üİ\H[YKœ\™—ØÛİ[\Š
Bˆ—ÛÚÈH]ØZ]ÚXÚ×Ù—ÚX[

Bˆ—Û][˜ŞWÛ\ÈH›İ[™

[YKœ\™—ØÛİ[\Š
HH—Üİ\
H
ˆLŠHYˆ—ÛÚÈ[ÙH›Û™B‚ˆ™Y\×Üİ\H[YKœ\™—ØÛİ[\Š
Bˆ™Y\×ÛÚÈH]ØZ]ÚXÚ×Ü™Y\×ÚX[

Bˆ™Y\×Û][˜ŞWÛ\ÈH›İ[™

[YKœ\™—ØÛİ[\Š
HH™Y\×Üİ\
H
ˆLŠHYˆ™Y\×ÛÚÈ[ÙH›Û™B‚ˆ™]\›ˆŞ\İ[RX[İ]
ˆ]X˜\ÙOY—ÛÚË]X˜\ÙWÛ][˜ŞWÛ\ÏY—Û][˜ŞWÛ\Ëˆ™Y\Ï\™Y\×ÛÚË™Y\×Û][˜ŞWÛ\Ï\™Y\×Û][˜ŞWÛ\Ëˆİ]\ÏH›ÚÈˆYˆ
—ÛÚÈ[™™Y\×ÛÚÊH[ÙH™YÜ˜YY‹ˆ\İ™\œÚ[Û\Ù][™ÜË”ÑT•’PÑWÕ‘T”ÒSÓ‹[š\›Û›Y[\Ù][™ÜËTÑS•‹ˆ\[YWÜÙXÛÛ™Ï\›İ[™
[YK[YJ
HH“ĞÑTÔ×ÔÕT•QĞUJKˆ
B‚ˆ›İ]\‹™Ù]
‹İ\Ù\œÈ‹™\ÜÛœÙWÛ[Ù[[\İÕ\Ù\“İ]JB˜\Ş[˜ÈYˆYZ[—Û\İİ\Ù\œÊˆNˆİˆ›Û™HH]Y\J›Û™JKˆ[Z]ˆ[H]Y\JLOLŒ
KˆÙ™œÙ]ˆ[H]Y\JÙOL
Kˆ\Ù\ˆ\Ù\ˆH\[™Ê™\]Z\™WÜ\›Z\ÜÚ[ÛŠ\Ù\œËœ™XYŠJKˆˆ\Ş[˜ÔÙ\ÜÚ[ÛˆH\[™ÊÙ]ÙŠKŠN‚ˆˆˆ”Ø[YH]Y\H\ÈÑUİ\Ù\œÈ8 %ZÙ\\™HÛÈ[™\ˆØYZ[ˆ™XØ]\ÙH]	ÜÂˆÚ\™HHYZ[ˆœ›Û[™
[™H›ÙXİ[Ûˆ]Y]
H^XİÈ]ˆˆˆ‚ˆİ]HÙ[Xİ
\Ù\ŠK›Ü[ÛœÊÙ[Xİ[›ØY
\Ù\‹œ›Û\ÊJKÚ\™J\Ù\‹™[]YØ]š\×Ê›Û™JJBˆYˆN‚ˆİ]Hİ]Ú\™J\Ù\‹™[XZ[š[ZÙJˆ‰^Ü_IHŠH\Ù\‹™[Û˜[YKš[ZÙJˆ‰^Ü_IHŠJBˆ™\İ[H]ØZ]‹™^Xİ]Jİ]›Ü™\—ØJ\Ù\‹˜Ü™X]YØ]™\ØÊ
JK›[Z]
[Z]
K›Ù™œÙ]
Ù™œÙ]
JBˆ\Ù\œÈH™\İ[œØØ[\œÊ
K˜[

Bˆ™]\›ˆÕ\Ù\“İ]
Y]KšY[XZ[]K™[XZ[[Û˜[YO]K™[Û˜[YK\×Ù[XZ[İ™\šYšYY]Kš\×Ù[XZ[İ™\šYšYYˆ\×ØXİ]™O]Kš\×ØXİ]™K›Û\ÏVÜ‹›˜[YH›Üˆˆ[ˆKœ›Û\×JH›ÜˆH[ˆ\Ù\œ×B‚‚›İ]\‹œÜİ
‹İ\Ù\œËŞİ\Ù\—ÚYKÙXXİ]˜]H‹™\ÜÛœÙWÛ[Ù[U\Ù\“İ]
B˜\Ş[˜ÈYˆXXİ]˜]Wİ\Ù\Šˆ\Ù\—ÚYˆ]ZY•URQˆYZ[ˆ\Ù\ˆH\[™Ê™\]Z\™WÜ\›Z\ÜÚ[ÛŠ\Ù\œË\]HŠJKˆˆ\Ş[˜ÔÙ\ÜÚ[ÛˆH\[™ÊÙ]ÙŠKŠN‚ˆ\™Ù]H
]ØZ]‹™^Xİ]JÙ[Xİ
\Ù\ŠKÚ\™J\Ù\‹šYOH\Ù\—ÚY
K›Ü[ÛœÊÙ[Xİ[›ØY
\Ù\‹œ›Û\ÊJJJKœØØ[\—ÛÛ™WÛÜ—Û›Û™J
BˆYˆ\™Ù]\È›Û™N‚ˆ˜Z\ÙH›İ›İ[™\œ›ÜŠ•\Ù\ˆ›İ›İ[™ˆŠBˆ\™Ù]š\×ØXİ]™HH˜[ÙBˆ]ØZ]™XÛÜ™Ø]Y]Ù]™[
‹XİÜ—ÚYXYZ[‹šYXİ[ÛH\Ù\‹™XXİ]˜]Y‹™\Ûİ\˜ÙWİ\OH\Ù\ˆ‹™\Ûİ\˜ÙWÚY\İŠ\Ù\—ÚY
JBˆ]ØZ]‹˜ÛÛ[Z]

Bˆ™]\›ˆ\Ù\“İ]
Y]\™Ù]šY[XZ[]\™Ù]™[XZ[[Û˜[YO]\™Ù]™[Û˜[YKˆ\×Ù[XZ[İ™\šYšYY]\™Ù]š\×Ù[XZ[İ™\šYšYY\×ØXİ]™O]\™Ù]š\×ØXİ]™Kˆ›Û\ÏVÜ‹›˜[YH›Üˆˆ[ˆ\™Ù]œ›Û\×JB‚‚›İ]\‹œÜİ
‹İ\Ù\œËŞİ\Ù\—ÚYKØXİ]˜]H‹™\ÜÛœÙWÛ[Ù[U\Ù\“İ]
B˜\Ş[˜ÈYˆXİ]˜]Wİ\Ù\Šˆ\Ù\—ÚYˆ]ZY•URQˆYZ[ˆ\Ù\ˆH\[™Ê™\]Z\™WÜ\›Z\ÜÚ[ÛŠ\Ù\œË\]HŠJKˆˆ\Ş[˜ÔÙ\ÜÚ[ÛˆH\[™ÊÙ]ÙŠKŠN‚ˆ\™Ù]H
]ØZ]‹™^Xİ]JÙ[Xİ
\Ù\ŠKÚ\™J\Ù\‹šYOH\Ù\—ÚY
K›Ü[ÛœÊÙ[Xİ[›ØY
\Ù\‹œ›Û\ÊJJJKœØØ[\—ÛÛ™WÛÜ—Û›Û™J
BˆYˆ\™Ù]\È›Û™N‚ˆ˜Z\ÙH›İ›İ[™\œ›ÜŠ•\Ù\ˆ›İ›İ[™ˆŠBˆ\™Ù]š\×ØXİ]™HHYBˆ]ØZ]™XÛÜ™Ø]Y]Ù]™[
‹XİÜ—ÚYXYZ[‹šYXİ[ÛH\Ù\‹˜Xİ]˜]Y‹™\Ûİ\˜ÙWİ\OH\Ù\ˆ‹™\Ûİ\˜ÙWÚY\İŠ\Ù\—ÚY
JBˆ]ØZ]‹˜ÛÛ[Z]

Bˆ™]\›ˆ\Ù\“İ]
Y]\™Ù]šY[XZ[]\™Ù]™[XZ[[Û˜[YO]\™Ù]™[Û˜[YKˆ\×Ù[XZ[İ™\šYšYY]\™Ù]š\×Ù[XZ[İ™\šYšYY\×ØXİ]™O]\™Ù]š\×ØXİ]™Kˆ›Û\ÏVÜ‹›˜[YH›Üˆˆ[ˆ\™Ù]œ›Û\×JB‚‚˜Û\ÜÈİÙ\’TŞ[˜Óİ]
˜\ÙS[Ù[
N‚ˆİ]\Îˆİ‚ˆ™X\ÛÛˆİˆ›Û™HH›Û™Bˆ]Nˆİˆ›Û™HH›Û™B‚‚›İ]\‹œÜİ
‹ÜİÙ\˜šKÜŞ[˜È‹™\ÜÛœÙWÛ[Ù[TİÙ\’TŞ[˜Óİ]
B˜\Ş[˜ÈYˆšYÙÙ\—ÜİÙ\˜šWÜŞ[˜ÊˆYZ[ˆ\Ù\ˆH\[™Ê™\]Z\™WÜ\›Z\ÜÚ[ÛŠ˜[˜[]XÜËšY]ÈŠJKˆˆ\Ş[˜ÔÙ\ÜÚ[ÛˆH\[™Ê3et_db),
):
    """Manual on-demand trigger for the daily Power BI aggregate-analytics
    push (same code path as the worker's scheduled job â€” see
    app/workers/worker.py::run_powerbi_sync) so an admin can test/verify-the
    integration without waiting for the next scheduled run. Returns
    status=skipÂed (not an error) if POWERBI_* env vars aren't configured."""
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
    db: AsyncSession = Depends(Í•Ñ}‘ˆ¤°(€€€á}µ…¥¹Ñ•¹…¹•}Í•É•ĞèÍÑÈğ9½¹”€ô!•…‘•È¡‘•™…Õ±Ğõ9½¹”¤°(¤è(€€€€ˆˆ‰•ÍÑÉÕÑ¥Ù”°•áÁ±¥¥Ñ±äµ…Ñ•µ…¥¹Ñ•¹…¹”•Í…Á”¡…Ñ è‘•±•Ñ•Ì•Ù•Éä(€€€ÕÍ•È…½Õ¹Ğ€¡…¹•Ù•ÉåÑ¡¥¹œÑ¡…ĞÉ•™•É•¹•Ì½¹”Ù¥„„É•…°™½É•¥¸(€€€­•ä€´´Í•ÍÍ¥½¹Ì°Ñ½­•¹Ì°•¹É½±±µ•¹ÑÌ°ÍÕ‰µ¥ÍÍ¥½¹Ì°•ÑŒ¸¤Ù¥„Ñ¡”Í…µ”(€€€QIU9Q€¸¸¸M…ÌÍÉ¥ÁÑÌ½É•Í•Ñ}…±±}…½Õ¹ÑÌ¹Áä¸((€€€•±¥‰•É…Ñ•±ä9=P‰•¡¥¹É•ÅÕ¥É•}Á•Éµ¥ÍÍ¥½¸ ¤½„ÕÍ•È)]P€´´Ñ¡”İ¡½±”(€€€Á½¥¹Ğ¥ÌÑ¼‰”ÕÍ…‰±”•Ù•¸İ¡•¸Ñ¡•É”…É”é•É¼İ½É­¥¹œ…½Õ¹ÑÌ±•™Ğ°(€€€½Èİ¡•¸Ñ¡”½¹±äÉ•‘•¹Ñ¥…°…Ù…¥±…‰±”¥ÌÑ¡¥Ì½¹”µÑ¥µ”Í•É•Ğ¸%¹ÍÑ•…(€€€¥ĞÌ…Ñ•‰ä5%9Q99}MIP°İ¡¥ ¥ÌÕ¹Í•Ğ‰ä‘•™…Õ±Ğ€¡9½¹”¤°Í¼(€€€Ñ¡¥Ì•¹‘Á½¥¹Ğ€ĞÀÑÌÕ¹±•ÍÌ…¸½Á•É…Ñ½È¡…Ì‘•±¥‰•É…Ñ•±ä½ÁÑ•¥¸‰ä(€€€Í•ÑÑ¥¹œÑ¡…Ğ•¹ØÙ…È€´´…¹¥ĞÌµ•…¹ĞÑ¼‰”Õ¹Í•Ğ……¥¸¥µµ•‘¥…Ñ•±ä(€€€…™Ñ•ÈÕÍ”¸á¥ÍÑÌ‰•…ÕÍ”I•¹‘•ÈÌ™É•”Ñ¥•È‘½•Í¸Ğ…±İ…åÌ½™™•È•…Íä(€€€¥¹Ñ•É…Ñ¥Ù”Í¡•±°…•ÍÌìÑ¡¥Ì¥ÌÑ¡”ÁÉ…Ñ¥…°…±Ñ•É¹…Ñ¥Ù”™½ÈÉÕ¹¹¥¹œ(€€€„É•…°‘•ÍÑÉÕÑ¥Ù”µ…¥¹Ñ•¹…¹”½Á•É…Ñ¥½¸……¥¹ÍĞÁÉ½‘ÕÑ¥½¸¸(€€€€ˆˆˆ(€€€¥˜¹½ĞÍ•ÑÑ¥¹Ì¹5%9Q99}MIPè(€€€€€€€É…¥Í”9½Ñ½Õ¹‘ÉÉ½È ‰9½Ğ™½Õ¹¸ˆ¤(€€€¥˜¹½Ğá}µ…¥¹Ñ•¹…¹•}Í•É•Ğ½Èá}µ…¥¹Ñ•¹…¹•}Í•É•Ğ€„ôÍ•ÑÑ¥¹Ì¹5%9Q99}MIPè(€€€€€€€€ŒM…µ”€ĞÀĞ…Ì€‰Õ¹½¹™¥ÕÉ•ˆ€´´‘½¸ĞÉ•Ù•…°Ñ¡…ĞÑ¡¥Ì•¹‘Á½¥¹Ğ(€€€€€€€€Œ•á¥ÍÑÌÑ¼„…±±•Èİ¡¼‘½•Í¸Ğ…±É•…‘ä¡…Ù”Ñ¡”Í•É•Ğ¸(€€€€€€€É…¥Í”9½Ñ½Õ¹‘ÉÉ½È ‰9½Ğ™½Õ¹¸ˆ¤((€€€…İ…¥Ğ‘ˆ¹•á•ÕÑ”¡Ñ•áĞ ‰QIU9QQ	1ÕÍ•ÉÌIMQIP%9Q%QdMˆ¤¤(€€€…İ…¥Ğ‘ˆ¹½µµ¥Ğ ¤((€€€É•ÑÕÉ¸5…¥¹Ñ•¹…¹•I•Í•Ñ=ÕĞ (€€€€€€€ÍÑ…ÑÕÌô‰½¬ˆ°(€€€€€€€‘•Ñ…¥°ô‰±°ÕÍ•È…½Õ¹ÑÌ€¡…¹•Ù•ÉåÑ¡¥¹œÉ•™•É•¹¥¹œÑ¡•´¤İ•É”‘•±•Ñ•¸I½±•Ì½Á•Éµ¥ÍÍ¥½¹Ì½‰…‘•Ìİ•É”±•™Ğ¥¹Ñ…Ğ¸ˆ°(€€€€¤