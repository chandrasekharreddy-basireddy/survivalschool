"""In-process scheduler for deployments that run only the web service.

Render (and the current infra) runs a single web service, not the standalone
worker in app/workers/worker.py, so the weekend AI exams and scheduled contests
would never fire in production. This loop runs those same idempotent ticks from
inside the web app.

A Redis leader lock (SET NX EX) guards each tick so that with multiple gunicorn
workers — or multiple app instances — exactly one runs the tick per interval;
everyone else skips it. The lock TTL is just under the interval so leadership is
re-contested each cycle rather than pinned to one process. If Redis is
unavailable the tick is simply skipped that cycle (logged), never duplicated.

This complements, and does not replace, the standalone worker: if a dedicated
worker/cron is deployed later, the lock keeps the two from double-running.
"""
from __future__ import annotations

import asyncio

import structlog

from app.database import AsyncSessionLocal
from app.redis_client import get_redis
from app.services.contest_service import (
    check_and_create_scheduled_contests,
    check_and_finalize_contests,
)
from app.services.exam_scheduler_service import (
    create_due_scheduled_exams,
    ensure_weekend_schedules,
    finalize_expired_scheduled_exams,
    issue_scheduled_exam_certificates,
)

logger = structlog.get_logger("survivalschool.scheduler")

TICK_SECONDS = 60
_LOCK_KEY = "scheduler:tick:leader"


async def _run_tick() -> None:
    async with AsyncSessionLocal() as db:
        ensured = await ensure_weekend_schedules(db)
        created = await create_due_scheduled_exams(db)
        finalized = await finalize_expired_scheduled_exams(db)
        issued = await issue_scheduled_exam_certificates(db)
    async with AsyncSessionLocal() as db:
        contests_created = await check_and_create_scheduled_contests(db)
        contests_finalized = await check_and_finalize_contests(db)

    if ensured or created or finalized or issued or contests_created or contests_finalized:
        logger.info(
            "scheduler_tick",
            weekend_schedules_ensured=ensured,
            exams_created=len(created),
            exams_finalized=finalized,
            certificates_issued=issued,
            contests_created=len(contests_created),
            contests_finalized=len(contests_finalized),
        )


async def scheduler_loop(stop: asyncio.Event) -> None:
    """Run the scheduler tick every TICK_SECONDS until `stop` is set."""
    logger.info("scheduler_loop_started", interval_seconds=TICK_SECONDS)
    while not stop.is_set():
        try:
            client = get_redis()
            # nx=only if absent, ex=auto-expire → single leader per interval.
            got_lock = await client.set(_LOCK_KEY, "1", nx=True, ex=TICK_SECONDS - 5)
            if got_lock:
                await _run_tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("scheduler_tick_failed", exc_info=True)
        try:
            await asyncio.wait_for(stop.wait(), timeout=TICK_SECONDS)
        except TimeoutError:
            pass
    logger.info("scheduler_loop_stopped")
