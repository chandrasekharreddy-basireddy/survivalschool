from __future__ import annotations

import redis.asyncio as redis

from app.config import get_settings

settings = get_settings()

_pool: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _pool
    if _pool is None:
        _pool = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _pool


async def check_redis_health() -> bool:
    try:
        client = get_redis()
        return await client.ping()
    except Exception:
        return False
