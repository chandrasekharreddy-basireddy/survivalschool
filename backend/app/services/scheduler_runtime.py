"""Shared scheduler-tick runtime, plus the in-process loop that drives it.

Render (and the current infra) runs a single web service, not the standalone
worker in app/workers/worker.py, so the weekend AI exams and scheduled contests
would never fire in production. scheduler_loop() below runs those same
idempotent ticks from inside the web app via FastAPI's lifespan.

A Redis leader lock (SET NX EX, token-owned) guards each tick so that with
multiple gunicorn workers — or multiple app instances, or a standalone worker
deployed alongside this — exactly one process runs the tick at a time. The
lock is renewed by a heartbeat while a tick is in flight (see
_run_locked_tick), so a slow tick can't let the TTL expire and let a second
process start a concurrent, overlapping run. If Redis is unavailable the tick
is simply skipped that cycle (logged), never duplicated.

app/workers/worker.py's standalone run_forever loop calls run_locked_tick()
too (see that module), so the same lock genuinely coordinates both — this
was previously just a docstring claim with no code backing it: the worker
ran on its own independent timer with zero Redis interaction.
"""
from __future__ import annotations

import asyncio
import secrets

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
# Comfortably longer than a tick is expected to take — the heartbeat renews
# well before this expires, so this TTL is really just "how stale can the
# lock get before we assume the holder died and let someone else take over,"
# not "how long a tick is allowed to run."
_LOCK_TTL_SECONDS = 120
_HEARTBEAT_INTERVAL_SECONDS = 30

# Renew only if the caller's token still matches the value stored in Redis —
# without this check, a heartbeat from a *previous* holder (e.g. one whose
# process is shutting down but hasn't cancelled its heartbeat task yet) could
# extend a lock now legitimately held by a different process.
_RENEW_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return 0
"""
# Release only if the caller's token still matches, for the same reason.
_RELEASE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


# Housekeeping jobs that don't need to run every minute, tracked by monotonic
# timestamp so the in-process scheduler can cover them without a second timer.
_HOUSEKEEPING_INTERVALS = {
    "cleanup_expired_tokens": 3600,
    "recompute_leaderboard_snapshot": 300,
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
    from app.workers.worker import cleanup_expired_tokens, recompute_leaderboard_snapshot

    jobs = {
        "cleanup_expired_tokens": cleanup_expired_tokens,
        "recompute_leaderboard_snapshot": recompute_leaderboard_snapshot,
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
        ensured = await ensure_weekend_schedules(db)
        created = await create_due_scheduled_exams(db)
        finalized = await finalize_expired_scheduled_exams(db)
        issued = await issue_scheduled_exam_certificates(db)
    async with AsyncSessionLocal() as db:
        contests_created = await check_and_create_scheduled_contests(db)
        contests_finalized = await check_and_finalize_contests(db)

    await _run_housekeeping()

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


async def _heartbeat(token: str, stop: asyncio.Event) -> None:
    client = get_redis()
    renew = client.register_script(_RENEW_LUA)
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=_HEARTBEAT_INTERVAL_SECONDS)
        except TimeoutError:
            pass
        if stop.is_set():
            return
        try:
            await renew(keys=[_LOCK_KEY], args=[token, _LOCK_TTL_SECONDS])
        except Exception:
            logger.warning("scheduler_lock_renew_failed", exc_info=True)


async def run_locked_tick() -> bool:
    """Try to become leader for one tick and, if successful, run it with the
    lock held (and renewed) for the whole duration. Returns True if this
    process ran the tick, False if another process already holds the lock
    or Redis is unavailable. Shared by both the in-process scheduler loop
    below and app/workers/worker.py's standalone loop, so the two can never
    run a tick concurrently regardless of which (or how many) are deployed.
    """
    token = secrets.token_urlsafe(16)
    try:
        client = get_redis()
        got_lock = await client.set(_LOCK_KEY, token, nx=True, ex=_LOCK_TTL_SECONDS)
    except Exception:
        logger.warning("scheduler_lock_acquire_failed", exc_info=True)
        return False
    if not got_lock:
        return False

    stop_heartbeat = asyncio.Event()
    heartbeat_task = asyncio.create_task(_heartbeat(token, stop_heartbeat))
    try:
        await _run_tick()
    finally:
        stop_heartbeat.set()
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except (asyncio.CancelledError, Exception):
            pass
        try:
            client = get_redis()
            release = client.register_script(_RELEASE_LUA)
            await release(keys=[_LOCK_KEY], args=[token])
        except Exception:
            logger.warning("scheduler_lock_release_failed", exc_info=True)
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
        try:
            await asyncio.wait_for(stop.wait(), timeout=TICK_SECONDS)
        except TimeoutError:
            pass
    logger.info("scheduler_loop_stopped")
