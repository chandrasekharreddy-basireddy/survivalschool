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
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete, func, select

from app.config import get_settings
from app.core.logging import configure_logging
from app.database import AsyncSessionLocal
from app.models.gamification import LeaderboardSnapshot, PointsLedger
from app.models.user import EmailVerification, PasswordReset, RefreshToken
from app.models.user import Session as SessionModel
from app.services.powerbi_service import sync_daily_engagement
from app.services.scheduler_runtime import run_locked_tick

logger = structlog.get_logger("survivalschool.worker")
settings = get_settings()


async def cleanup_expired_tokens() -> None:
    """Hard-deletes long-expired, already-used-or-dead auth tokens/sessions —
    keeps the tables small and removes any residual sensitive material past
    its useful life (spec section 50: data retention)."""
    cutoff = datetime.now(UTC) - timedelta(days=30)
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


async def run_scheduler_tick() -> None:
    """Runs the shared weekend-exam + contest scheduling tick (see
    app/services/scheduler_runtime.py) behind its Redis leader lock.

    This is the SAME lock, and the SAME tick logic, that the in-process
    scheduler (app/services/scheduler_runtime.py, driven from the web app's
    lifespan) uses. Previously this worker called the exam/contest service
    functions directly on its own independent timer with no Redis
    coordination at all — the two schedulers' claimed mutual exclusion was a
    docstring promise the code didn't keep. If a standalone worker replica is
    ever deployed alongside the default single-web-service topology (or
    scaled to multiple worker replicas), run_locked_tick() ensures only one
    of them — worker or web — actually runs a given tick.
    """
    ran = await run_locked_tick()
    if not ran:
        logger.debug("scheduler_tick_skipped_not_leader")


async def run_powerbi_sync() -> None:
    """Pushes yesterday's aggregate engagement stats to Power BI (see
    app/services/powerbi_service.py). No-op, logged, if POWERBI_* env vars
    aren't set — same inert-by-default pattern as send_inactivity_reminders'
    n8n dependency."""
    async with AsyncSessionLocal() as db:
        result = await sync_daily_engagement(db)
    logger.info("powerbi_sync_job_done", status=result["status"])


JOBS = [
    # Same 60s cadence as scheduler_runtime.TICK_SECONDS, since both compete
    # for the same lock and only one of them will actually run any given tick.
    # cleanup_expired_tokens and recompute_leaderboard_snapshot are NOT listed
    # separately here — they now run inside that locked tick
    # (scheduler_runtime._run_housekeeping, on their own 1h/5min intervals) so
    # they also happen on deployments that run no worker at all. Listing them
    # here too would double-run them outside the lock.
    (run_scheduler_tick, 60),
    (run_powerbi_sync, 86400),  # once daily — pushes yesterday's aggregate stats
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
