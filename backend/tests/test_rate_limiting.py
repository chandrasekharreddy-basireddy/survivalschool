from __future__ import annotations

import uuid

import pytest

from app.core.exceptions import RateLimitedError
from app.services.rate_limit_service import enforce_rate_limit


async def test_rate_limiter_blocks_after_threshold():
    key = f"unit-test:{uuid.uuid4()}"
    for _ in range(3):
        await enforce_rate_limit(key, limit=3, window_seconds=60)

    with pytest.raises(RateLimitedError):
        await enforce_rate_limit(key, limit=3, window_seconds=60)


async def test_rate_limiter_is_scoped_per_key():
    key_a = f"unit-test:{uuid.uuid4()}"
    key_b = f"unit-test:{uuid.uuid4()}"
    for _ in range(3):
        await enforce_rate_limit(key_a, limit=3, window_seconds=60)
    # A different key must not be affected by key_a's usage.
    await enforce_rate_limit(key_b, limit=3, window_seconds=60)
