"""Redis-backed fixed-window rate limiter for sensitive endpoints (spec section 49).

Degrades open (allows the request) if Redis is unavailable rather than taking
the whole app down — logged loudly so it's visible in monitoring. This is a
deliberate resilience choice per spec section 48 ("if Redis fails, application
should degrade gracefully where possible"); the tradeoff is documented in
SECURITY.md.
"""
from __future__ import annotations

import structlog

from app.core.exceptions import RateLimitedError
from app.redis_client import get_redis

logger = structlog.get_logger("survivalschool.ratelimit")


async def enforce_rate_limit(key: str, *, limit: int, window_seconds: int) -> None:
    try:
        client = get_redis()
        redis_key = f"ratelimit:{key}"
        current = await client.incr(redis_key)
        if current == 1:
            await client.expire(redis_key, window_seconds)
        if current > limit:
            raise RateLimitedError(
                "Too many requests. Try again in a few minutes.",
                details={"limit": limit, "window_seconds": window_seconds},
            )
    except RateLimitedError:
        raise
    except Exception:
        logger.warning("rate_limit_degraded_open", key=key)
        return
