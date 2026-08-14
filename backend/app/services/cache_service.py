"""Real Redis-backed read-through caching for hot, expensive-to-recompute
endpoints (contest leaderboards, the public course catalog, the global
points leaderboard).

Two patterns, matching the two real invalidation shapes in this app:

1. **Direct key** (`cache_get_json`/`cache_set_json`/`cache_delete`) — for
   data keyed by a single resource id, e.g. one contest's leaderboard. The
   write path that changes that resource deletes its exact key.

2. **Versioned namespace** (`cache_get_versioned`/`cache_set_versioned`/
   `bump_cache_version`) — for list/aggregate endpoints with many possible
   query-param combinations (search, pagination, filters), where enumerating
   every cached variant to delete on a write is impractical. Every cache key
   in the namespace embeds the namespace's current version number; bumping
   the version on any write makes every previously-cached variant
   unreachable (and therefore effectively evicted) in O(1), without a Redis
   SCAN/KEYS pattern-delete (which is a real production anti-pattern — it
   blocks the single-threaded Redis event loop on a large keyspace).

Matches the existing rate_limit_service.py convention: **degrade open** on
any Redis error. A cache is an optimization, not a source of truth — if
Redis is down, every request just falls through to Postgres exactly like it
did before this file existed, logged loudly so it's visible in monitoring,
never a 500.
"""
from __future__ import annotations

import json
from typing import Any

import structlog

from app.redis_client import get_redis

logger = structlog.get_logger("survivalschool.cache")

_PREFIX = "cache"


async def cache_get_json(key: str) -> Any | None:
    try:
        raw = await get_redis().get(f"{_PREFIX}:{key}")
        return json.loads(raw) if raw is not None else None
    except Exception:
        logger.warning("cache_get_degraded", key=key)
        return None


async def cache_set_json(key: str, value: Any, ttl_seconds: int) -> None:
    try:
        await get_redis().set(f"{_PREFIX}:{key}", json.dumps(value, default=str), ex=ttl_seconds)
    except Exception:
        logger.warning("cache_set_degraded", key=key)


async def cache_delete(*keys: str) -> None:
    if not keys:
        return
    try:
        await get_redis().delete(*(f"{_PREFIX}:{k}" for k in keys))
    except Exception:
        logger.warning("cache_delete_degraded", keys=keys)


async def bump_cache_version(namespace: str) -> None:
    """Call this from every write path that can change what a versioned-
    namespace endpoint would return. Missing one just means that namespace
    can serve stale reads for up to its TTL — not a hard failure — but every
    real write path in this codebase that touches a cached namespace does
    call this, so treat a newly-cached endpoint's write paths as needing
    this too."""
    try:
        await get_redis().incr(f"{_PREFIX}:ver:{namespace}")
    except Exception:
        logger.warning("cache_bump_degraded", namespace=namespace)


async def _get_version(namespace: str) -> int:
    try:
        v = await get_redis().get(f"{_PREFIX}:ver:{namespace}")
        return int(v) if v is not None else 0
    except Exception:
        return 0


async def cache_get_versioned(namespace: str, key: str) -> Any | None:
    version = await _get_version(namespace)
    return await cache_get_json(f"{namespace}:v{version}:{key}")


async def cache_set_versioned(namespace: str, key: str, value: Any, ttl_seconds: int) -> None:
    version = await _get_version(namespace)
    await cache_set_json(f"{namespace}:v{version}:{key}", value, ttl_seconds)
