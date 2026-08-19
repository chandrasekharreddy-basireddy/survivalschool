"""Real Power BI REST API integration — service-principal (Azure AD app
registration, client credentials grant) OAuth2 flow, then pushes aggregate
platform analytics into a Power BI "push dataset" via the Power BI REST API.

Deliberately inert when POWERBI_TENANT_ID/POWERBI_CLIENT_ID/
POWERBI_CLIENT_SECRET/POWERBI_WORKSPACE_ID are unset — same inert-by-default
pattern as app/services/push_service.py (VAPID keys) and
app/services/n8n_service.py (webhook URL): a real deployment sets real,
per-deployment Azure AD app credentials via env vars; nothing here is a
fabricated credential.

Only aggregate counts/rates are pushed — never raw rows keyed by email or
any other PII (spec section 50: data minimization). Source data comes from
`analytics_events`, `quiz_attempts`, `daily_challenge_attempts`, and `points`
— the same tables docs/POWERBI.md already documents as the ones worth
building reports on.

See docs/POWERBI.md for setup (Azure AD app registration, workspace access
grant, the four env vars) and the exact dataset/table schema pushed here.
"""
from __future__ import annotations

import time
from datetime import UTC, date, datetime, timedelta

import httpx
import structlog
from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from app.models.challenge import DailyChallengeAttempt
from app.models.gamification import PointsLedger
from app.models.system import AnalyticsEvent

logger = structlog.get_logger("survivalschool.powerbi")
settings = get_settings()

AAD_TOKEN_URL_TMPL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
POWERBI_API_BASE = "https://api.powerbi.com/v1.0/myorg"
POWERBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"

DATASET_NAME = "SurvivalSchool Daily Engagement"
TABLE_NAME = "DailyEngagement"

# Push-dataset schema. Deliberately aggregate-only columns — no user_id,
# email, or any other per-student identifier (spec section 50).
TABLE_SCHEMA = {
    "name": TABLE_NAME,
    "columns": [
        {"name": "Date", "dataType": "DateTime"},
        {"name": "ActiveStudents", "dataType": "Int64"},
        {"name": "QuizAttempts", "dataType": "Int64"},
        {"name": "QuizPassRate", "dataType": "Double"},
        {"name": "AverageQuizScore", "dataType": "Double"},
        {"name": "DailyChallengeCompletions", "dataType": "Int64"},
        {"name": "DailyChallengeCorrectRate", "dataType": "Double"},
        {"name": "PointsAwarded", "dataType": "Int64"},
    ],
}

# In-memory token cache — a single process-wide bearer token, refreshed a
# little before expiry. Fine for a low-frequency (daily) sync job; a
# multi-replica deployment just means each replica gets its own token,
# which Azure AD is fine with (it's not a per-instance secret).
_token_cache: dict = {"access_token": None, "expires_at": 0.0}

# Dataset existence is checked/created once per process lifetime, not on
# every push — Power BI's "create if not exists" is not idempotent (it
# would create a duplicate dataset each call), so we track it ourselves.
_dataset_ensured = False


def powerbi_configured() -> bool:
    return bool(
        settings.POWERBI_TENANT_ID
        and settings.POWERBI_CLIENT_ID
        and settings.POWERBI_CLIENT_SECRET
        and settings.POWERBI_WORKSPACE_ID
    )


async def _get_access_token() -> str:
    """Client-credentials OAuth2 flow against Azure AD v2 endpoint. Caches
    the token in-process and refreshes 60s before actual expiry."""
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]

    url = AAD_TOKEN_URL_TMPL.format(tenant=settings.POWERBI_TENANT_ID)
    data = {
        "grant_type": "client_credentials",
        "client_id": settings.POWERBI_CLIENT_ID,
        "client_secret": settings.POWERBI_CLIENT_SECRET,
        "scope": POWERBI_SCOPE,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, data=data)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("powerbi_token_request_failed", error=str(exc))
        raise ServiceUnavailableError("Power BI authentication failed.", code="powerbi_auth_failed") from exc

    body = resp.json()
    token = body["access_token"]
    expires_in = int(body.get("expires_in", 3600))
    _token_cache["access_token"] = token
    _token_cache["expires_at"] = now + expires_in
    return token


async def _pbi_request(method: str, path: str, *, json: dict | None = None) -> httpx.Response:
    token = await _get_access_token()
    url = f"{POWERBI_API_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.request(
                method, url, json=json,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp
    except httpx.HTTPError as exc:
        logger.warning("powerbi_api_request_failed", path=path, error=str(exc))
        raise ServiceUnavailableError("Power BI API request failed.", code="powerbi_api_failed") from exc


async def ensure_dataset() -> str:
    """Finds the push dataset by name in the configured workspace, creating
    it (with the schema above) if it doesn't exist yet. Returns the
    dataset ID. Cheap no-op after the first successful call in a process
    (see _dataset_ensured)."""
    global _dataset_ensured

    group_id = settings.POWERBI_WORKSPACE_ID
    resp = await _pbi_request("GET", f"/groups/{group_id}/datasets")
    existing = resp.json().get("value", [])
    for ds in existing:
        if ds.get("name") == DATASET_NAME:
            _dataset_ensured = True
            return ds["id"]

    create_resp = await _pbi_request(
        "POST",
        f"/groups/{group_id}/datasets?defaultRetentionPolicy=basicFIFO",
        json={
            "name": DATASET_NAME,
            "defaultMode": "Push",
            "tables": [TABLE_SCHEMA],
        },
    )
    dataset_id = create_resp.json()["id"]
    logger.info("powerbi_dataset_created", dataset_id=dataset_id)
    _dataset_ensured = True
    return dataset_id


async def push_rows(dataset_id: str, rows: list[dict]) -> None:
    """POSTs rows into the push dataset's table. Power BI's push-dataset API
    caps a single POST at 10,000 rows / 15MB — nowhere near our daily-row
    volume, so no batching is needed here."""
    if not rows:
        return
    group_id = settings.POWERBI_WORKSPACE_ID
    await _pbi_request(
        "POST",
        f"/groups/{group_id}/datasets/{dataset_id}/tables/{TABLE_NAME}/rows",
        json={"rows": rows},
    )


async def compute_daily_engagement(db: AsyncSession, *, day: date) -> dict:
    """Aggregates one calendar day (UTC) of platform activity into the row
    shape pushed to Power BI. Pure aggregation — no PII, no per-student rows.
    """
    start = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
    end = start + timedelta(days=1)

    active_students = (
        await db.execute(
            select(func.count(func.distinct(AnalyticsEvent.user_id))).where(
                AnalyticsEvent.occurred_at >= start,
                AnalyticsEvent.occurred_at < end,
                AnalyticsEvent.user_id.isnot(None),
            )
        )
    ).scalar_one()

    from app.models.assessment import QuizAttempt

    quiz_stats = (
        await db.execute(
            select(
                func.count(QuizAttempt.id),
                func.avg(QuizAttempt.score_percent),
                func.sum(func.cast(QuizAttempt.passed, Integer)),
            ).where(
                QuizAttempt.submitted_at >= start,
                QuizAttempt.submitted_at < end,
                QuizAttempt.status == "submitted",
            )
        )
    ).one()
    quiz_attempts, avg_score, passed_count = quiz_stats
    quiz_attempts = int(quiz_attempts or 0)
    passed_count = int(passed_count or 0)
    quiz_pass_rate = (passed_count / quiz_attempts) if quiz_attempts else 0.0
    average_quiz_score = float(avg_score) if avg_score is not None else 0.0

    challenge_stats = (
        await db.execute(
            select(
                func.count(DailyChallengeAttempt.id),
                func.sum(func.cast(DailyChallengeAttempt.is_correct, Integer)),
            ).where(
                DailyChallengeAttempt.created_at >= start,
                DailyChallengeAttempt.created_at < end,
            )
        )
    ).one()
    challenge_completions, correct_count = challenge_stats
    challenge_completions = int(challenge_completions or 0)
    correct_count = int(correct_count or 0)
    challenge_correct_rate = (correct_count / challenge_completions) if challenge_completions else 0.0

    points_awarded = (
        await db.execute(
            select(func.coalesce(func.sum(PointsLedger.amount), 0)).where(
                PointsLedger.created_at >= start,
                PointsLedger.created_at < end,
            )
        )
    ).scalar_one()

    return {
        "Date": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "ActiveStudents": int(active_students or 0),
        "QuizAttempts": quiz_attempts,
        "QuizPassRate": round(quiz_pass_rate, 4),
        "AverageQuizScore": round(average_quiz_score, 2),
        "DailyChallengeCompletions": challenge_completions,
        "DailyChallengeCorrectRate": round(challenge_correct_rate, 4),
        "PointsAwarded": int(points_awarded),
    }


async def sync_daily_engagement(db: AsyncSession, *, day: date | None = None) -> dict:
    """Full sync entry point: computes yesterday's (or the given day's)
    aggregate engagement row and pushes it to the Power BI push dataset,
    creating the dataset/table if this is the first run.

    No-ops (returns a status dict, does not raise) when Power BI isn't
    configured — callers (the daily worker job and the admin manual-trigger
    endpoint) never need to check powerbi_configured() themselves, matching
    the inert-by-default pattern of push_service.send_to_user / n8n_service.emit_event.
    """
    if not powerbi_configured():
        logger.info("powerbi_not_configured", action="sync_daily_engagement_skipped")
        return {"status": "skipped", "reason": "powerbi_not_configured"}

    target_day = day or (datetime.now(UTC).date() - timedelta(days=1))
    row = await compute_daily_engagement(db, day=target_day)

    dataset_id = await ensure_dataset()
    await push_rows(dataset_id, [row])

    logger.info("powerbi_daily_sync_complete", date=row["Date"], dataset_id=dataset_id)
    return {"status": "synced", "date": row["Date"], "row": row, "dataset_id": dataset_id}
