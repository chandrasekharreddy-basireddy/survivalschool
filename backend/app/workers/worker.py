"""Background worker process (spec section 31).

Deliberately a plain asyncio loop rather than a heavier queue framework —
the job set here is small, periodic, and doesn't need per-task retries with
backoff yet. Each job is independent and swallow-and-log on failure so one
broken job never stops the others. For request-triggered async work (e.g. a
burst of AI calls) this would grow into a real queue (Celery/arq + Redis);
noted as a scaling follow-up in docs/ARCHITECTURE.md.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import delete, func, select

from app.config import get_settings
from app.core.logging import configure_logging
from app.database import AsyncSessionLocal
from app.models.gamification import LeaderboardSnapshot, PointsLedger
from app.models.lms import CourseProgress
from app.models.user import EmailVerification, PasswordReset, RefreshToken
from app.models.user import Session as SessionModel
from app.services.email_service import send_email
from app.services.n8n_service import emit_event

logger = structlog.get_logger("survivalschool.worker")
settings = get_settings()


async def cleanup_expired_tokens() -> None:
    """Hard-deletes long-expired, already-used-or-dead auth tokens/sessions —
    keeps the tables small and removes any residual sensitive material past
    its useful life (spec section 50: data retention)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    async with AsyncSessionLocal() as db:
        for model in (EmailVerification, PasswordReset):
            await db.execute(delete(model).where(model.expires_at < cutoff))
        await db.execute(delete(RefreshToken).where(RefreshToken.expires_at < cutoff))
        await db.execute(delete(SessionModel).where(SessionModel.revoked_at.isnot(None), SessionModel.updated_at < cutoff))
        await db.commit()
    logger.info("cleanup_expired_tokens_done")


async def recompute_leaderboard_snapshot() -> None:
    """Materializes the global leaderboard so reads never hit a live
    aggregate over the whole points ledger (spec section 16)."""
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(PointsLedger.student_id, func.sum(PointsLedger.amount).label("total"))
            .group_by(PointsLedger.student_id)
            .order_by(func.sum(PointsLedger.amount).desc())
            .limit(100)
        )).all()
        await db.execute(delete(LeaderboardSnapshot).where(LeaderboardSnapshot.scope == "global"))
        for rank, (student_id, total) in enumerate(rows, start=1):
            db.add(LeaderboardSnapshot(scope="global", student_id=student_id, rank=rank, total_points=int(total)))
        await db.commit()
    logger.info("leaderboard_snapshot_recomputed", entries=len(rows))


async def send_inactivity_reminders() -> None:
    """Nudges students who made progress but haven't returned in 7+ days —
    mirrors the n8n 'inactive student -> engagement reminder' workflow
    (spec section 20) but runs natively too, so the reminder still fires even
    if the n8n automation layer is down (spec section 48: n8n failing must
    never break core functionality)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    async with AsyncSessionLocal() as db:
        stalled = (await db.execute(
            select(CourseProgress).where(
                CourseProgress.percent_complete > 0, CourseProgress.percent_complete < 100,
                CourseProgress.updated_at < cutoff,
            ).limit(50)
        )).scalars().all()
        for progress in stalled:
            from app.models.lms import Course
            from app.models.user import User
            student = await db.get(User, progress.student_id)
            course = await db.get(Course, progress.course_id)
            if not student or not course:
                continue
            await send_email(
                student.email, "We saved your spot", "inactivity_reminder",
                full_name=student.full_name, course_title=course.title,
                percent_complete=progress.percent_complete,
                resume_url=f"{settings.FRONTEND_URL}/courses/{course.slug}",
            )
            await emit_event("student.inactive", {
                "email": student.email, "full_name": student.full_name,
                "course_title": course.title, "percent_complete": progress.percent_complete,
            })
    logger.info("inactivity_reminders_sent", count=len(stalled))


JOBS = [
    (cleanup_expired_tokens, 3600),
    (recompute_leaderboard_snapshot, 300),
    (send_inactivity_reminders, 86400),
]


async def run_forever() -> None:
    configure_logging()
    logger.info("worker_started", jobs=[j.__name__ for j, _ in JOBS])
    last_run: dict[str, float] = {}
    loop = asyncio.get_event_loop()

    while True:
        now = loop.time()
        for job, interval in JOBS:
            if now - last_run.get(job.__name__, 0) >= interval:
                try:
                    await job()
                except Exception as exc:
                    logger.error("job_failed", job=job.__name__, error=str(exc))
                last_run[job.__name__] = now
        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(run_forever())
