"""Redis-backed fixed-window rate limiter for sensitive endpoints (spec section 49).

Degrades open (allows the request) if Redis is unavailable rather than taking
the whole app down — logged loudly so it's visible in monitoring. This is a
deliberate resilience choice per spec section 48 ("if Redis fails, application
should degrade gracefully where possible"); the tradeoff is documented in
SECURITY.md.

The counter increment and its TTL are applied in a single Lua script so they
are atomic. Doing them as two round-trips (INCR then EXPIRE) leaves a window
where a crash or dropped connection between the two calls strands the counter
key with no TTL, which permanently locks the caller out of login, registration
and password reset with no recovery path short of manual Redis surgery. The
script also re-arms the TTL whenever it finds a key without one, so any keys
already stranded by the previous implementation heal themselves on next use.
"""
from __future__ import annotations

import structlog

from app.core.exceptions import RateLimitedError
from app.redis_client import get_redis

logger = structlog.get_logger("survivalschool.ratelimit")

# KEYS[1] = counter key, ARGV[1] = window in seconds. Returns the new count.
_INCR_WITH_TTL_LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 or redis.call('TTL', KEYS[1]) < 0 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""

_script = None


def _get_script():
    """Register the Lua script once per process (uses EVALSHA after first run)."""
    global _script
    if _script is None:
        _script = get_redis().register_script(_INCR_WITH_TTL_LUA)
    return _script


async def enforce_rate_limit(key: str, *, limit: int, window_seconds: int, fail_closed: bool = False) -> None:
    try:
        redis_key = f"ratelimit:{key}"
        current = int(await _get_script()(keys=[redis_key], args=[window_seconds]))
        if current > limit:
            raise RateLimitedError(
                "Too many requests. Try again in a few minutes.",
                details={"limit": limit, "window_seconds": window_seconds},
            )
    except RateLimitedError:
        raise
    except Exception as exc:
        if fail_closed:
            logger.warning("rate_limit_fail_closed", key=key)
            raise RateLimitedError(
                "Unable to verify rate limit. Please try again later.",
                details={"limit": limit, "window_seconds": window_seconds},
            ) from exc
        logger.warning("rate_limit_degraded_open", key=key)
        return
