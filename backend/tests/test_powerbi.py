from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.database import AsyncSessionLocal
from app.models.gamification import PointsLedger
from app.models.system import AnalyticsEvent
from app.services import powerbi_service
from tests.conftest import auth_headers, grant_role

pytestmark = pytest.mark.asyncio(loop_scope="session")

_REAL_POST = httpx.AsyncClient.post
_REAL_REQUEST = httpx.AsyncClient.request


def _passthrough_for_asgi(mock: AsyncMock, real_method):
    """Wraps a mock so calls from an httpx.AsyncClient using ASGITransport
    (i.e. this test suite's own `client` fixture talking to our FastAPI app)
    fall through to the real implementation, while calls from a plain
    network-transport AsyncClient (i.e. powerbi_service's real outbound
    calls to Azure AD / Power BI) hit the mock. This lets us assert on the
    Power BI HTTP calls without breaking the test client's own requests,
    since both use httpx.AsyncClient under the hood."""

    async def _dispatch(self, *args, **kwargs):
        if isinstance(self._transport, httpx.ASGITransport):
            return await real_method(self, *args, **kwargs)
        return await mock(*args, **kwargs)

    return _dispatch


def _configure_powerbi(monkeypatch):
    """Force POWERBI_* to look configured for a test, regardless of what the
    real running environment has set (mirrors how test_push.py handles
    VAPID: it reads real settings when present, but here we need
    deterministic "configured" state for both branches of the test matrix)."""
    monkeypatch.setattr(powerbi_service.settings, "POWERBI_TENANT_ID", "test-tenant")
    monkeypatch.setattr(powerbi_service.settings, "POWERBI_CLIENT_ID", "test-client")
    monkeypatch.setattr(powerbi_service.settings, "POWERBI_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(powerbi_service.settings, "POWERBI_WORKSPACE_ID", "test-workspace")
    powerbi_service._token_cache["access_token"] = None
    powerbi_service._token_cache["expires_at"] = 0.0
    powerbi_service._dataset_ensured = False


def _unconfigure_powerbi(monkeypatch):
    monkeypatch.setattr(powerbi_service.settings, "POWERBI_TENANT_ID", None)
    monkeypatch.setattr(powerbi_service.settings, "POWERBI_CLIENT_ID", None)
    monkeypatch.setattr(powerbi_service.settings, "POWERBI_CLIENT_SECRET", None)
    monkeypatch.setattr(powerbi_service.settings, "POWERBI_WORKSPACE_ID", None)


async def test_inert_when_unconfigured_no_http_call(monkeypatch):
    """Core inert-by-default assertion: with any POWERBI_* var unset, syncing
    must be a pure no-op — no Azure AD token request, no Power BI API call."""
    _unconfigure_powerbi(monkeypatch)
    assert powerbi_service.powerbi_configured() is False

    with patch("httpx.AsyncClient.post") as mock_post, patch("httpx.AsyncClient.request") as mock_request:
        async with AsyncSessionLocal() as db:
            result = await powerbi_service.sync_daily_engagement(db)

    assert result == {"status": "skipped", "reason": "powerbi_not_configured"}
    mock_post.assert_not_called()
    mock_request.assert_not_called()


async def test_inert_when_partially_configured_no_http_call(monkeypatch):
    """Any single missing var (not just all four) must also keep it inert —
    a half-configured deployment must not attempt a doomed API call."""
    _configure_powerbi(monkeypatch)
    monkeypatch.setattr(powerbi_service.settings, "POWERBI_CLIENT_SECRET", None)
    assert powerbi_service.powerbi_configured() is False

    with patch("httpx.AsyncClient.post") as mock_post:
        async with AsyncSessionLocal() as db:
            result = await powerbi_service.sync_daily_engagement(db)

    assert result["status"] == "skipped"
    mock_post.assert_not_called()


async def test_token_acquisition_uses_correct_client_credentials_grant(monkeypatch):
    _configure_powerbi(monkeypatch)

    mock_token_response = AsyncMock()
    mock_token_response.raise_for_status = lambda: None
    mock_token_response.json = lambda: {"access_token": "fake-aad-token", "expires_in": 3600}

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_token_response)) as mock_post:
        token = await powerbi_service._get_access_token()

    assert token == "fake-aad-token"
    assert mock_post.await_count == 1
    call = mock_post.await_args
    url = call.args[0]
    assert url == "https://login.microsoftonline.com/test-tenant/oauth2/v2.0/token"
    body = call.kwargs["data"]
    assert body["grant_type"] == "client_credentials"
    assert body["client_id"] == "test-client"
    assert body["client_secret"] == "test-secret"
    assert body["scope"] == "https://analysis.windows.net/powerbi/api/.default"

    # Cached — a second call within expiry must not re-request.
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_token_response)) as mock_post2:
        token2 = await powerbi_service._get_access_token()
    assert token2 == "fake-aad-token"
    mock_post2.assert_not_called()


async def test_ensure_dataset_creates_with_correct_schema_when_absent(monkeypatch):
    _configure_powerbi(monkeypatch)
    powerbi_service._token_cache["access_token"] = "cached-token"
    powerbi_service._token_cache["expires_at"] = 9999999999.0

    list_resp = AsyncMock()
    list_resp.raise_for_status = lambda: None
    list_resp.json = lambda: {"value": []}

    create_resp = AsyncMock()
    create_resp.raise_for_status = lambda: None
    create_resp.json = lambda: {"id": "new-dataset-id"}

    with patch("httpx.AsyncClient.request", new=AsyncMock(side_effect=[list_resp, create_resp])) as mock_req:
        dataset_id = await powerbi_service.ensure_dataset()

    assert dataset_id == "new-dataset-id"
    assert mock_req.await_count == 2

    list_call, create_call = mock_req.await_args_list
    assert list_call.args[0] == "GET"
    assert list_call.args[1] == "https://api.powerbi.com/v1.0/myorg/groups/test-workspace/datasets"

    assert create_call.args[0] == "POST"
    assert "test-workspace" in create_call.args[1]
    payload = create_call.kwargs["json"]
    assert payload["name"] == powerbi_service.DATASET_NAME
    assert payload["defaultMode"] == "Push"
    table = payload["tables"][0]
    assert table["name"] == "DailyEngagement"
    column_names = {c["name"] for c in table["columns"]}
    assert column_names == {
        "Date", "ActiveStudents", "QuizAttempts", "QuizPassRate",
        "AverageQuizScore", "DailyChallengeCompletions",
        "DailyChallengeCorrectRate", "PointsAwarded",
    }
    # No PII columns.
    assert "email" not in column_names and "UserId" not in column_names


async def test_ensure_dataset_reuses_existing_dataset(monkeypatch):
    _configure_powerbi(monkeypatch)
    powerbi_service._token_cache["access_token"] = "cached-token"
    powerbi_service._token_cache["expires_at"] = 9999999999.0

    list_resp = AsyncMock()
    list_resp.raise_for_status = lambda: None
    list_resp.json = lambda: {"value": [{"id": "existing-id", "name": powerbi_service.DATASET_NAME}]}

    with patch("httpx.AsyncClient.request", new=AsyncMock(return_value=list_resp)) as mock_req:
        dataset_id = await powerbi_service.ensure_dataset()

    assert dataset_id == "existing-id"
    assert mock_req.await_count == 1  # no create call


async def test_compute_daily_engagement_aggregation_math(client, monkeypatch):
    """Seeds known rows for a specific UTC day and asserts the aggregate
    numbers Power BI would receive are exactly right — proves the
    aggregation logic, independent of any network mocking."""
    target_day = date(2026, 1, 15)
    start = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)

    student_ids = []
    for _ in range(3):
        email, _headers = await auth_headers(client)
        from sqlalchemy import select as _select

        from app.models.user import User as _User
        async with AsyncSessionLocal() as db:
            u = (await db.execute(_select(_User).where(_User.email == email.lower()))).scalar_one()
            student_ids.append(u.id)

    async with AsyncSessionLocal() as db:

        # 2 distinct active students via analytics events.
        db.add(AnalyticsEvent(event_type="lesson.viewed", user_id=student_ids[0], occurred_at=start))
        db.add(AnalyticsEvent(event_type="lesson.viewed", user_id=student_ids[1], occurred_at=start))
        db.add(AnalyticsEvent(event_type="lesson.viewed", user_id=student_ids[0], occurred_at=start))  # dup, same student
        # Outside the target day — must not be counted.
        db.add(AnalyticsEvent(event_type="lesson.viewed", user_id=student_ids[2], occurred_at=start - timedelta(days=2)))

        # Points: 100 + 50 inside window, 999 outside window.
        db.add(PointsLedger(student_id=student_ids[0], amount=100, reason="quiz_pass"))
        db.add(PointsLedger(student_id=student_ids[1], amount=50, reason="lesson_complete"))
        outside_points = PointsLedger(student_id=student_ids[2], amount=999, reason="streak")
        db.add(outside_points)
        await db.flush()
        # Force timestamps directly since Timestamped uses server_default now().
        await db.execute(
            PointsLedger.__table__.update()
            .where(PointsLedger.student_id == student_ids[0])
            .values(created_at=start)
        )
        await db.execute(
            PointsLedger.__table__.update()
            .where(PointsLedger.student_id == student_ids[1])
            .values(created_at=start)
        )
        await db.execute(
            PointsLedger.__table__.update()
            .where(PointsLedger.id == outside_points.id)
            .values(created_at=start - timedelta(days=5))
        )
        await db.commit()

    result = await _compute_with_isolated_data(target_day, start, student_ids)
    assert result["ActiveStudents"] == 2
    assert result["PointsAwarded"] == 150
    assert result["Date"] == "2026-01-15T00:00:00"


async def _compute_with_isolated_data(target_day, start, student_ids):
    async with AsyncSessionLocal() as db:
        return await powerbi_service.compute_daily_engagement(db, day=target_day)


async def test_manual_sync_endpoint_requires_admin(client):
    _, headers = await auth_headers(client)
    resp = await client.post("/admin/powerbi/sync", headers=headers)
    assert resp.status_code == 403


async def test_manual_sync_endpoint_requires_auth(client):
    resp = await client.post("/admin/powerbi/sync")
    assert resp.status_code == 401


async def test_manual_sync_endpoint_skips_when_unconfigured(client, monkeypatch):
    email, headers = await auth_headers(client)
    await grant_role(email, "ADMIN")
    _unconfigure_powerbi(monkeypatch)

    # ASGITransport calls (the test client talking to our own app) pass
    # through untouched; only real outbound httpx.AsyncClient.post calls
    # (i.e. powerbi_service's Azure AD/Power BI calls) hit the mock — see
    # _passthrough_for_asgi.
    mock_post = AsyncMock()
    with patch.object(httpx.AsyncClient, "post", _passthrough_for_asgi(mock_post, _REAL_POST)):
        resp = await client.post("/admin/powerbi/sync", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "skipped"
    assert body["reason"] == "powerbi_not_configured"
    mock_post.assert_not_called()


async def test_manual_sync_endpoint_pushes_row_when_configured(client, monkeypatch):
    email, headers = await auth_headers(client)
    await grant_role(email, "ADMIN")
    _configure_powerbi(monkeypatch)

    token_resp = AsyncMock()
    token_resp.raise_for_status = lambda: None
    token_resp.json = lambda: {"access_token": "fake-token", "expires_in": 3600}

    list_resp = AsyncMock()
    list_resp.raise_for_status = lambda: None
    list_resp.json = lambda: {"value": [{"id": "ds-1", "name": powerbi_service.DATASET_NAME}]}

    push_resp = AsyncMock()
    push_resp.raise_for_status = lambda: None
    push_resp.json = lambda: {}

    mock_token_post = AsyncMock(return_value=token_resp)
    mock_req = AsyncMock(side_effect=[list_resp, push_resp])
    with patch.object(httpx.AsyncClient, "post", _passthrough_for_asgi(mock_token_post, _REAL_POST)), \
         patch.object(httpx.AsyncClient, "request", _passthrough_for_asgi(mock_req, _REAL_REQUEST)):
        resp = await client.post("/admin/powerbi/sync", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "synced"
    assert mock_token_post.await_count == 1
    assert mock_req.await_count == 2  # list datasets, push rows

    push_call = mock_req.await_args_list[1]
    assert push_call.args[0] == "POST"
    assert "tables/DailyEngagement/rows" in push_call.args[1]
    rows = push_call.kwargs["json"]["rows"]
    assert len(rows) == 1
    assert set(rows[0].keys()) == {
        "Date", "ActiveStudents", "QuizAttempts", "QuizPassRate",
        "AverageQuizScore", "DailyChallengeCompletions",
        "DailyChallengeCorrectRate", "PointsAwarded",
    }
