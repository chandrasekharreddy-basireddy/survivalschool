"""Shared scheduler-tick runtime, plus the in-process loop that drives it.

Render (and the current infra) runs a single web service, not the standalone
worker in app/workers/worker.py, so the scheduled contests would never fire
in production. scheduler_loop() below runs those same idempotent ticks from
inside the web app via FastAPI's lifespan.

Uses the shared distributed-lock helper (services/distributed_lock.py) so
that with multiple gunicorn workers — or multiple app instances, or a
standalone worker deployed alongside this — exactly one process runs the
tick at a time. If Redis is unavailable the tick is simply skipped that
cycle (logged), never duplicated.

Elimination battles are NOT driven from this tick — a strict 15-second
per-question deadline can't wait behind a 60s cadence built for
hourly/weekly jobs. See elimination_service.py's own, much tighter sweep
loop, started separately from the same app lifespan (main.py).
"""
from __future__ import annotations

import asyncio
import contextlib

import structlog

from app.database import AsyncSessionLocal
from app.services.contest_service import (
    check_and_create_scheduled_contests,
    check_and_finalize_contests,
)
from app.services.distributed_lock import try_lock

logger = structlog.get_logger("survivalschool.scheduler")

TICK_SECONDS = 60
_LOCK_KEY = "scheduler:tick:leader"
# Comfortably longer than a tick is expected to take — the heartbeat renews
# well before this expires, so this TTL is really just "how stale can the
# lock get before we assume the holder died and let someone else take over,"
# not "how long a tick is allowed to run."
_LOCK_TTL_SECONDS = 120
_HEARTBEAT_INTERVAL_SECONDS = 30


# Housekeeping jobs that don't need to run every minute, tracked by monotonic
# timestamp so the in-process scheduler can cover them without a second timer.
_HOUSEKEEPING_INTERVALS = {
    "cleanup_expired_tokens": 3600,
    "recompute_leaderboard_snapshot": 300,
    # This is a floor on how often we even check, not the actual sync
    # interval — sync_campus_timetable_if_due reads
    # CampusTimetableSource.poll_interval_minutes itself and no-ops until
    # that's elapsed. 300s just keeps a short configured interval (the
    # schema's minimum is 5 minutes) reasonably responsive.
    "sync_campus_timetable_if_due": 300,
}
_last_housekeeping_run: dict[str, float] = {}


async def _run_housekeeping() -> None:
    """Run the periodic maintenance jobs that would otherwise only ever run
    in the standalone worker.

    On the real deployment target (a single Render web service, no worker),
    expired-token cleanup and the leaderboard snapshot were silently never
    running: they're defined in app/workers/worker.py's JOBS list, which
    nothing executes there. Leaderboard reads then fall back to a live
    aggregate and dead auth tokens accumulate forever. Imported lazily to
    avoid a circular import (worker imports run_locked_tick from this module).
    """
    from app.services.campus_timetable_service import sync_campus_timetable_if_due
    from app.workers.worker import cleanup_expired_tokens, recompute_leaderboard_snapshot

    jobs = {
        "cleanup_expired_tokens": cleanup_expired_tokens,
        "recompute_leaderboard_snapshot": recompute_leaderboard_snapshot,
        "sync_campus_timetable_if_due": sync_campus_timetable_if_due,
    }
    now = asyncio.get_running_loop().time()
    for name, job in jobs.items():
        interval = _HOUSEKEEPING_INTERVALS[name]
        if now - _last_housekeeping_run.get(name, 0.0) < interval:
            continue
        try:
            await job()
        except Exception:
            # One failing housekeeping job must not abort the rest of the tick.
            logger.warning("housekeeping_job_failed", job=name, exc_info=True)
        _last_housekeeping_run[name] = now


async def _run_tick() -> None:
    async with AsyncSessionLocal() as db:
        contests_created = await check_and_create_scheduled_contests(db)
        contests_finalized = await check_and_finalize_contests(db)

    await _run_housekeeping()

    if contests_created or contests_finalized:
        logger.info(
            "scheduler_tick",
            contests_created=len(contests_created),
            contests_finalized=len(contests_finalized),
        )


async def run_locked_tick() -> bool:
    """Try to become leader for one tick and, if successful, run it with the
    lock held (and renewed) for the whole duration. Returns True if this
    process ran the tick, False if another process already holds the lock
    or Redis is unavailable. Shared by both the in-process scheduler loop
    below and app/workers/worker.py's standalone loop, so the two can never
    run a tick concurrently regardless of which (or how many) are deployed.
    """
    async with try_lock(_LOCK_KEY, ttl_seconds=_LOCK_TTL_SECONDS, heartbeat_interval_seconds=_HEARTBEAT_INTERVAL_SECONDS) as got_lock:
        if not got_lock:
            return False
        await _run_tick()
        return True


async def scheduler_loop(stop: asyncio.Event) -> None:
    """Run a locked scheduler tick every TICK_SECONDS until `stop` is set."""
    logger.info("scheduler_loop_started", interval_seconds=TICK_SECONDS)
    while not stop.is_set():
        try:
            await run_locked_tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("scheduler_tick_failed", exc_info=True)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=TICK_SECONDS)
    logger.info("scheduler_loop_stopped")
