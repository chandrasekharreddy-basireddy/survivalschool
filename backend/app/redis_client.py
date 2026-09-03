from __future__ import annotations

import redis.asyncio as redis

from app.config import get_settings

settings = get_settings()

_pool: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _pool
    if _pool is None:
        # socket_connect_timeout only bounds establishing the TCP connection —
        # it does NOT apply to an already-open connection's blocking reads, so
        # it's safe for the long-lived pub/sub listener in websockets/manager.py
        # too. Without it, an unreachable/unresponsive Redis (firewall drop,
        # network blip, wrong security group) stalls every call for the OS's
        # default TCP connect timeout instead of failing fast into the
        # degrade-open fallback every caller in cache_service.py /
        # rate_limit_service.py / distributed_lock.py already assumes.
        _pool = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2)
    return _pool


async def check_redis_health() -> bool:
    try:
        client = get_redis()
        return await client.ping()
    except Exception:
        return False
