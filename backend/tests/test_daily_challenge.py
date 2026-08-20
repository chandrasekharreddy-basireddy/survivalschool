from __future__ import annotations

import pytest

from tests.conftest import auth_headers, grant_role, login

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _make_instructor(client):
    email, headers = await auth_headers(client)
    await grant_role(email, "INSTRUCTOR")
    tokens = await login(client, email)
    return email, {"Authorization": f"Bearer {tokens['access_token']}"}


async def _make_admin(client):
    email, headers = await auth_headers(client)
    await grant_role(email, "ADMIN")
    tokens = await login(client, email)
    return email, {"Authorization": f"Bearer {tokens['access_token']}"}


async def _seed_subject_and_topic(client, admin_headers, name="Daily"):
    import uuid as uuid_mod
    unique = uuid_mod.uuid4().hex[:8]
    subject_resp = await client.post(
        "/subjects", json={"name": f"Subject {unique}", "slug": f"subj-{unique}"}, headers=admin_headers,
    )
    assert subject_resp.status_code == 201, subject_resp.text
    subject_id = subject_resp.json()["id"]
    topic_resp = await client.post(
        f"/subjects/{subject_id}/topics", json={"name": f"Topic {unique}", "slug": f"topic-{unique}"}, headers=admin_headers,
    )
    assert topic_resp.status_code == 201, topic_resp.text
    return subject_id, topic_resp.json()["id"]


async def _seed_question(client, instructor_headers, prompt="Daily Q", admin_headers=None):
    """Only used to guarantee at least one single/true_false Question exists
    in case this is the very first test in the whole suite to touch
    /daily-challenge — the *content* of the seeded question is irrelevant to
    every test below, since which real question ends up being "today's" is
    a shared, date-keyed singleton (see docs/ENGAGEMENT.md): whichever
    request reaches GET /daily-challenge/today first for the day wins, and
    every test in this session shares one Postgres instance (see
    tests/conftest.py's session-scoped _setup_database fixture) — so tests
    below look up the real correct option directly via the DB rather than
    assuming their own freshly-seeded question is the one in play."""
    if admin_headers is None:
        _, admin_headers = await _make_admin(client)
    subject_id, topic_id = await _seed_subject_and_topic(client, admin_headers)
    q_resp = await client.post(
        "/questions",
        json={
            "subject_id": subject_id, "topic_id": topic_id, "prompt": prompt, "question_type": "single", "points": 1,
            "options": [
                {"text": "Wrong", "is_correct": False, "order_index": 0},
                {"text": "Right", "is_correct": True, "order_index": 1},
            ],
        },
        headers=instructor_headers,
    )
    assert q_resp.status_code == 201, q_resp.text
    return q_resp.json()


async def _correct_option_id(question_id: str) -> str:
    """Looks up the real answer key directly in Postgres — the server never
    sends is_correct to a client before it has answered, so this is the only
    way a test can know the right answer for whatever question ended up
    being today's (see _seed_question's docstring)."""
    import uuid as uuid_mod

    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.assessment import QuestionOption

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(QuestionOption).where(
                QuestionOption.question_id == uuid_mod.UUID(question_id), QuestionOption.is_correct == True  # noqa: E712
            )
        )
        option = result.scalars().first()
        assert option is not None, "seeded question always has exactly one correct option"
        return str(option.id)


async def test_requires_verified_auth(client):
    resp = await client.get("/daily-challenge/today")
    assert resp.status_code == 401


async def test_get_todays_challenge_returns_a_real_question_with_no_correctness_leaked(client):
    _, instructor_headers = await _make_instructor(client)
    await _seed_question(client, instructor_headers, prompt="Ensure At Least One Question Exists")

    _, student_headers = await auth_headers(client)
    resp = await client.get("/daily-challenge/today", headers=student_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["already_attempted"] is False
    assert body["my_attempt"] is None
    assert len(body["question"]["options"]) >= 2
    assert all("is_correct" not in o for o in body["question"]["options"])


async def test_todays_challenge_is_the_same_question_for_every_student(client):
    _, headers_a = await auth_headers(client)
    _, headers_b = await auth_headers(client)
    resp_a = await client.get("/daily-challenge/today", headers=headers_a)
    resp_b = await client.get("/daily-challenge/today", headers=headers_b)
    assert resp_a.status_code == 200 and resp_b.status_code == 200
    assert resp_a.json()["id"] == resp_b.json()["id"]
    assert resp_a.json()["question"]["id"] == resp_b.json()["question"]["id"]


async def test_correct_answer_awards_points_and_updates_streak(client):
    _, student_headers = await auth_headers(client)
    today = (await client.get("/daily-challenge/today", headers=student_headers)).json()
    correct_id = await _correct_option_id(today["question"]["id"])

    before_stats = (await client.get("/gamification/me", headers=student_headers)).json()

    resp = await client.post(
        "/daily-challenge/today/attempt", json={"selected_option_ids": [correct_id]}, headers=student_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["already_attempted"] is True
    assert body["my_attempt"]["is_correct"] is True
    assert body["my_attempt"]["points_awarded"] == 15
    assert body["current_streak_days"] >= 1

    after_stats = (await client.get("/gamification/me", headers=student_headers)).json()
    assert after_stats["total_points"] == before_stats["total_points"] + 15
    assert after_stats["current_streak_days"] >= 1


async def test_wrong_answer_awards_zero_points_but_still_counts_as_activity(client):
    _, student_headers = await auth_headers(client)
    today = (await client.get("/daily-challenge/today", headers=student_headers)).json()
    correct_id = await _correct_option_id(today["question"]["id"])
    wrong_id = next(o["id"] for o in today["question"]["options"] if o["id"] != correct_id)

    resp = await client.post(
        "/daily-challenge/today/attempt", json={"selected_option_ids": [wrong_id]}, headers=student_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["my_attempt"]["is_correct"] is False
    assert body["my_attempt"]["points_awarded"] == 0
    # Correctness is only revealed AFTER a real attempt exists for this student.
    assert correct_id in body["my_attempt"]["correct_option_ids"]
    assert body["current_streak_days"] >= 1


async def test_cannot_submit_twice_same_day(client):
    _, student_headers = await auth_headers(client)
    today = (await client.get("/daily-challenge/today", headers=student_headers)).json()
    any_option = today["question"]["options"][0]["id"]

    resp1 = await client.post("/daily-challenge/today/attempt", json={"selected_option_ids": [any_option]}, headers=student_headers)
    assert resp1.status_code == 200

    resp2 = await client.post("/daily-challenge/today/attempt", json={"selected_option_ids": [any_option]}, headers=student_headers)
    assert resp2.status_code == 422


async def test_history_reflects_todays_attempt(client):
    _, student_headers = await auth_headers(client)
    today = (await client.get("/daily-challenge/today", headers=student_headers)).json()
    any_option = today["question"]["options"][0]["id"]
    await client.post("/daily-challenge/today/attempt", json={"selected_option_ids": [any_option]}, headers=student_headers)

    history = await client.get("/daily-challenge/history", headers=student_headers)
    assert history.status_code == 200
    entries = history.json()
    assert len(entries) >= 1
    assert entries[0]["challenge_date"] == today["challenge_date"]
