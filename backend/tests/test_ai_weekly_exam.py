"""AI Weekly Exam: topic difficulty scoring and registration gating.

Regression coverage for a real bug caught only by live browser testing (no
existing test exercised this path): evaluate_topic_difficulty built a query
using avg(count(...)) in one SELECT, which Postgres rejects outright as
nested aggregates (GroupingError). Every call to GET /topics/{id}/difficulty
— the endpoint the AI Weekly Exam registration page depends on to show
eligibility — 500'd unconditionally.
"""
from __future__ import annotations

import pytest

from tests.conftest import auth_headers, grant_role, login

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _make_admin(client):
    email, headers = await auth_headers(client)
    await grant_role(email, "ADMIN")
    tokens = await login(client, email)
    return email, {"Authorization": f"Bearer {tokens['access_token']}"}


async def _make_instructor(client):
    email, headers = await auth_headers(client)
    await grant_role(email, "INSTRUCTOR")
    tokens = await login(client, email)
    return email, {"Authorization": f"Bearer {tokens['access_token']}"}


async def _seed_subject_and_topic(client, admin_headers):
    import uuid as uuid_mod
    unique = uuid_mod.uuid4().hex[:8]
    subject_id = (await client.post("/subjects", json={"name": f"Subject {unique}", "slug": f"subj-{unique}"}, headers=admin_headers)).json()["id"]
    topic_id = (await client.post(f"/subjects/{subject_id}/topics", json={"name": f"Topic {unique}", "slug": f"topic-{unique}"}, headers=admin_headers)).json()["id"]
    return subject_id, topic_id


async def test_topic_difficulty_endpoint_does_not_500_with_multiple_questions(client):
    """The exact scenario that triggered the nested-aggregate GroupingError:
    more than one validated question on a topic, so the avg-of-per-question-
    option-counts query actually has multiple groups to average over."""
    _, admin = await _make_admin(client)
    _, instructor = await _make_instructor(client)
    subject_id, topic_id = await _seed_subject_and_topic(client, admin)

    for i in range(3):
        resp = await client.post("/questions", json={
            "subject_id": subject_id, "topic_id": topic_id, "prompt": f"Q{i}?", "question_type": "single", "points": 1,
            "options": [
                {"text": "Right", "is_correct": True, "order_index": 0},
                {"text": "Wrong1", "is_correct": False, "order_index": 1},
                {"text": "Wrong2", "is_correct": False, "order_index": 2},
            ],
        }, headers=instructor)
        assert resp.status_code == 201, resp.text

    resp = await client.get(f"/topics/{topic_id}/difficulty", headers=admin)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sample_size"] == 0  # no historical answers yet
    assert 0 <= body["difficulty_percent"] <= 100
    assert "3 validated question(s)" in body["reason"]
    assert "avg 3.0 options" in body["reason"]


async def test_topic_difficulty_endpoint_handles_topic_with_no_questions(client):
    _, admin = await _make_admin(client)
    _, topic_id = await _seed_subject_and_topic(client, admin)

    resp = await client.get(f"/topics/{topic_id}/difficulty", headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.json()["difficulty_percent"] == 0
    assert resp.json()["eligible_for_ai_exam"] is False


async def test_ai_weekly_registration_status_is_public_and_never_gates_signup(client):
    """Account signup must stay open every day — only AI Weekly Exam
    registration is Thursday-gated. This endpoint is what the frontend
    registration page reads; there is deliberately no equivalent gate on
    POST /auth/register."""
    resp = await client.get("/contests/ai-weekly/registration-status")
    assert resp.status_code == 200
    body = resp.json()
    assert "is_open" in body and "message" in body

    # Signup itself must succeed regardless of the AI-weekly window.
    email, headers = await auth_headers(client)
    me = await client.get("/auth/me", headers=headers)
    assert me.status_code == 200
