"""Regression test for a real bug found only by reading app/main.py during a
pre-deploy audit: a global HTTP middleware (`registration_window_guard`)
intercepted every POST /auth/register and rejected it with 403 unless the
AI Weekly Exam's Thursday-only registration window happened to be open —
directly contradicting the explicit product requirement that account
signup stays open every day (only the AI Weekly Exam's own registration is
Thursday-gated, via /contests/ai-weekly/register).

This went completely undetected by the rest of the suite because the
middleware short-circuited itself under APP_ENV == "test" (see the
conftest.py-set env var), so no test ever exercised the code path that
actually rejected a registration. It would only have started rejecting
signups the first non-Thursday after the day this was tested manually.

Since the test harness's APP_ENV="test" bypass makes it impractical to
exercise the real 403 path end-to-end here, this guards the regression
structurally instead: no middleware in the app's stack may intercept and
conditionally reject POST /auth/register at all. If a future change adds
one back, this fails loudly regardless of what day the suite happens to
run on.
"""
from __future__ import annotations

import pytest

from app.main import app


def test_no_middleware_gates_account_registration():
    suspect_names = {"registration_window_guard", "registration_guard", "signup_window_guard"}
    for mw in app.user_middleware:
        name = getattr(mw.cls, "__name__", "") or ""
        func = getattr(mw, "kwargs", {}).get("dispatch") if hasattr(mw, "kwargs") else None
        func_name = getattr(func, "__name__", "") if func else ""
        assert name not in suspect_names, f"found a registration-gating middleware: {name}"
        assert func_name not in suspect_names, f"found a registration-gating middleware: {func_name}"


@pytest.mark.asyncio(loop_scope="session")
async def test_register_succeeds_regardless_of_ai_weekly_registration_window_state(client):
    """Belt-and-suspenders: even with the AI Weekly Exam's registration
    window forced closed, account signup must still succeed."""
    from app.database import AsyncSessionLocal
    from app.services.registration_service import get_or_create_window

    async with AsyncSessionLocal() as db:
        window = await get_or_create_window(db)
        window.is_open = False
        window.override_until = None
        await db.commit()

    from tests.conftest import unique_email, unique_username

    email = unique_email()
    resp = await client.post("/auth/register", json={"email": email, "password": "Sup3r$ecretPass1", "full_name": "Always Open", "username": unique_username()})
    assert resp.status_code == 201, resp.text
