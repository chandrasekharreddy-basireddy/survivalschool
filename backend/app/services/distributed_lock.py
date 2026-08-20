"""Reusable Redis distributed lock: SET NX EX with an owner token, renewed by
a heartbeat while held, released only by whoever's token still matches.
Extracted from scheduler_runtime.py's inline scheduler-tick lock (which
still owns its own copy scoped to the global tick — this is the same
pattern, generalized for a caller-supplied key) so elimination_service.py
can take a per-battle lock without duplicating the four Lua/heartbeat
snippets a second time.
"""
from __future__ import annotations

import asyncio
import contextlib
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog

from app.redis_client import get_redis

logger = structlog.get_logger("survivalschool.lock")

_RENEW_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


@asynccontextmanager
async def try_lock(key: str, *, ttl_seconds: int = 30, heartbeat_interval_seconds: int = 10) -> AsyncIterator[bool]:
    """Yields True if this call acquired the lock (and holds it, renewed,
    for the duration of the `async with` block), False if another holder
    already has it or Redis is unavailable. Caller must check the yielded
    value — entering the block does not mean the lock was acquired."""
    token = secrets.token_urlsafe(16)
    try:
        client = get_redis()
        got_lock = await client.set(key, token, nx=True, ex=ttl_seconds)
    except Exception:
        logger.warning("lock_acquire_failed", key=key, exc_info=True)
        got_lock = False

    if not got_lock:
        yield False
        return

    stop_heartbeat = asyncio.Event()

    async def _heartbeat() -> None:
        client = get_redis()
        renew = client.register_script(_RENEW_LUA)
        while not stop_heartbeat.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop_heartbeat.wait(), timeout=heartbeat_interval_seconds)
            if stop_heartbeat.is_set():
                return
            with contextlib.suppress(Exception):
                await renew(keys=[key], args=[token, ttl_seconds])

    heartbeat_task = asyncio.create_task(_heartbeat())
    try:
        yield True
    finally:
        stop_heartbeat.set()
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await heartbeat_task
        with contextlib.suppress(Exception):
            client = get_redis()
            release = client.register_script(_RELEASE_LUA)
            await release(keys=[key], args=[token])
