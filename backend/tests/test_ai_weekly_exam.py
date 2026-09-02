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


async def _force_ai_weekly_window_open(client):
    """Registration is real-calendar Thursday-gated; force it open so these
    tests are deterministic regardless of what day the suite runs on.

    register_for_ai_weekly_exam() checks ai_exam_registration_is_open(now,
    window.override_until) directly — it never reads window.is_open (that
    field is a display cache refresh_window() maintains for the public
    /registration-status endpoint). override_until is the field that
    actually gates registration, so that's what has to be forced here."""
    from datetime import UTC, datetime, timedelta

    from app.database import AsyncSessionLocal
    from app.services.registration_service import get_or_create_window

    async with AsyncSessionLocal() as db:
        window = await get_or_create_window(db)
        window.override_until = datetime.now(UTC) + timedelta(hours=1)
        await db.commit()


async def _make_student(client):
    return await auth_headers(client)


async def test_ai_weekly_register_accepts_free_text_subject_and_topic(client):
    """The subject/topic are freely typed by the student now — no dropdown,
    no pre-existing Subject/Topic row required. The mock AI provider scores
    a longer, multi-word topic description as eligible (see
    MockAIProvider.evaluate_topic_scope)."""
    await _force_ai_weekly_window_open(client)
    _, student = await _make_student(client)

    resp = await client.post("/contests/ai-weekly/register", json={
        "subject_name": "Computer Science", "topic_name": "Graph Algorithms and Shortest Paths",
    }, headers=student)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "registered"
    assert body["contest_title"]

    # The free-text subject/topic really did create real taxonomy rows —
    # confirmable via the ordinary admin-visible subjects listing.
    subjects = (await client.get("/subjects")).json()
    assert any(s["name"] == "Computer Science" for s in subjects)


async def test_ai_weekly_register_rejects_too_vague_topic_with_score_details(client):
    """A short, one-word topic scores low/inappropriate under the mock
    heuristic — the 422 must carry the score so the frontend can explain
    why, not just a bare message."""
    await _force_ai_weekly_window_open(client)
    _, student = await _make_student(client)

    resp = await client.post("/contests/ai-weekly/register", json={
        "subject_name": "Math", "topic_name": "Numbers",
    }, headers=student)
    assert resp.status_code == 422, resp.text
    details = resp.json()["error"]["details"]
    assert "difficulty_percent" in details
    assert "is_appropriate_scope" in details


async def test_ai_weekly_register_rejects_topic_identical_to_subject(client):
    await _force_ai_weekly_window_open(client)
    _, student = await _make_student(client)

    resp = await client.post("/contests/ai-weekly/register", json={
        "subject_name": "Chemistry", "topic_name": "Chemistry",
    }, headers=student)
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["details"]["difficulty_percent"] == 0


async def test_ai_weekly_register_same_topic_twice_is_idempotent(client):
    """Registering for the same (subject, topic) a second time returns the
    same attempt rather than erroring or double-registering."""
    await _force_ai_weekly_window_open(client)
    _, student = await _make_student(client)
    payload = {"subject_name": "Biology", "topic_name": "Cellular Respiration and Metabolism"}

    first = await client.post("/contests/ai-weekly/register", json=payload, headers=student)
    assert first.status_code == 201, first.text
    second = await client.post("/contests/ai-weekly/register", json=payload, headers=student)
    assert second.status_code == 201, second.text
    assert first.json()["attempt_id"] == second.json()["attempt_id"]


async def test_ai_weekly_register_reuses_existing_subject_case_insensitively(client):
    """Two students typing "Physics" and "physics" land on the same Subject
    row rather than creating a duplicate."""
    await _force_ai_weekly_window_open(client)
    _, student_a = await _make_student(client)
    _, student_b = await _make_student(client)

    await client.post("/contests/ai-weekly/register", json={
        "subject_name": "Physics", "topic_name": "Quantum Mechanics Fundamentals",
    }, headers=student_a)
    await client.post("/contests/ai-weekly/register", json={
        "subject_name": "physics", "topic_name": "Quantum Mechanics Fundamentals",
    }, headers=student_b)

    subjects = [s for s in (await client.get("/subjects")).json() if s["name"].lower() == "physics"]
    assert len(subjects) == 1


async def test_profile_institute_is_optional_and_persists(client):
    """The registration page auto-fills this from the profile once set."""
    _, student = await _make_student(client)

    before = await client.get("/users/me/profile", headers=student)
    assert before.status_code == 200
    assert before.json()["institute"] is None

    patched = await client.patch("/users/me/profile", json={"institute": "Sai University"}, headers=student)
    assert patched.status_code == 200
    assert patched.json()["institute"] == "Sai University"

    again = await client.get("/users/me/profile", headers=student)
    assert again.json()["institute"] == "Sai University"


async def test_ai_weekly_wins_leaderboard_counts_only_rank_one_by_username(client):
    """"Who wins the most AI conducted exams" — rank-1 finishes only, shown
    by public username, not every top-3 certificate holder."""
    import uuid as uuid_mod
    from datetime import UTC, datetime, timedelta

    from app.database import AsyncSessionLocal
    from app.models.contest import Contest

    await _force_ai_weekly_window_open(client)
    _, winner = await _make_student(client)
    runner_up_email, runner_up = await _make_student(client)

    reg = await client.post("/contests/ai-weekly/register", json={
        "subject_name": "History", "topic_name": "20th Century Global Conflicts and Diplomacy",
    }, headers=winner)
    assert reg.status_code == 201, reg.text
    contest_id = reg.json()["contest_id"]

    # Runner-up registers into the SAME (topic, week) contest too.
    reg2 = await client.post("/contests/ai-weekly/register", json={
        "subject_name": "History", "topic_name": "20th Century Global Conflicts and Diplomacy",
    }, headers=runner_up)
    assert reg2.status_code == 201, reg2.text
    assert reg2.json()["contest_id"] == contest_id

    # The auto-generated contest's real slot is a future Saturday — open the
    # window now so the attempt flow (start/submit) can actually run in-test.
    # A generous 20s close (not immediate) so both students have real time
    # to start/submit before manual_finalize_contest's own "hasn't closed
    # yet" guard would reject it.
    async with AsyncSessionLocal() as db:
        contest = await db.get(Contest, uuid_mod.UUID(contest_id))
        now = datetime.now(UTC)
        contest.starts_at = now - timedelta(minutes=1)
        contest.ends_at = now + timedelta(seconds=20)
        await db.commit()

    handle = await client.patch("/users/me/profile", json={"public_handle": "history_champ"}, headers=winner)
    assert handle.status_code == 200, handle.text
    handle2 = await client.patch("/users/me/profile", json={"public_handle": "history_runnerup"}, headers=runner_up)
    assert handle2.status_code == 200, handle2.text

    for headers, get_right in ((winner, True), (runner_up, False)):
        start = await client.post(f"/contests/{contest_id}/attempts", headers=headers)
        assert start.status_code == 201, start.text
        qs = (await client.get(f"/contests/attempts/{start.json()['attempt_id']}/questions", headers=headers)).json()
        answers = [
            {"question_id": q["id"], "selected_option_ids": [q["options"][0 if get_right else 1]["id"]]}
            for q in qs
        ]
        submitted = await client.post(f"/contests/attempts/{start.json()['attempt_id']}/submit", json={"answers": answers}, headers=headers)
        assert submitted.status_code == 200, submitted.text

    import asyncio
    await asyncio.sleep(20.3)

    _, admin = await _make_admin(client)
    finalize = await client.post(f"/contests/{contest_id}/finalize", headers=admin)
    assert finalize.status_code == 200, finalize.text

    board = await client.get("/contests/ai-weekly/leaderboard")
    assert board.status_code == 200, board.text
    entries = board.json()
    winner_entry = next((e for e in entries if e["public_handle"] == "history_champ"), None)
    assert winner_entry is not None, entries
    assert winner_entry["wins"] == 1
    assert winner_entry["rank"] == 1
    # The runner-up placed #2 (a real top-3 certificate, since top_n_awarded
    # defaults to 3) but never ranked #1 anywhere, so "wins" must exclude them.
    assert not any(e["public_handle"] == "history_runnerup" for e in entries), entries


async def test_submitting_a_partial_answer_set_does_not_inflate_the_score(client):
    """Regression test for a real scoring-integrity bug: submit_contest_attempt
    used to compute points_possible only from the questions present in
    payload.answers, which has no completeness requirement. A student could
    get a perfect score_percent by simply omitting every question they
    weren't confident about from the submitted payload entirely, instead of
    submitting a wrong/blank answer for it — the "possible points"
    denominator shrank to match whatever they chose to answer. Answering
    exactly one question correctly and omitting the rest must score well
    below 100%, reflecting the full fixed question set the attempt was
    actually assigned (question_order), not just what was submitted."""
    import uuid as uuid_mod
    from datetime import UTC, datetime, timedelta

    from app.database import AsyncSessionLocal
    from app.models.contest import Contest

    await _force_ai_weekly_window_open(client)
    _, student = await _make_student(client)

    reg = await client.post("/contests/ai-weekly/register", json={
        "subject_name": "Mathematics", "topic_name": "Linear Algebra and Matrix Operations",
    }, headers=student)
    assert reg.status_code == 201, reg.text
    contest_id = reg.json()["contest_id"]

    async with AsyncSessionLocal() as db:
        contest = await db.get(Contest, uuid_mod.UUID(contest_id))
        now = datetime.now(UTC)
        contest.starts_at = now - timedelta(minutes=1)
        contest.ends_at = now + timedelta(minutes=5)
        await db.commit()

    # Question generation runs as a fire-and-forget asyncio.create_task
    # kicked off during registration (see get_or_create_ai_weekly_contest /
    # _generate_ai_weekly_questions_in_background in ai_exam_service.py) — in
    # production there's always a multi-day gap before starts_at, but here
    # nothing paces the test against it, so poll until it lands instead of
    # racing it (starting an attempt before question_ids is populated is
    # correctly rejected with a 409 "still being prepared").
    import asyncio

    for _ in range(50):
        async with AsyncSessionLocal() as db:
            contest = await db.get(Contest, uuid_mod.UUID(contest_id))
            if contest.question_ids:
                break
        await asyncio.sleep(0.2)
    else:
        raise AssertionError("AI weekly question generation did not complete in time")

    start = await client.post(f"/contests/{contest_id}/attempts", headers=student)
    assert start.status_code == 201, start.text
    qs = (await client.get(f"/contests/attempts/{start.json()['attempt_id']}/questions", headers=student)).json()
    assert len(qs) > 1, "need more than one question for this test to prove anything"

    # Answer only the FIRST question, correctly. Every other question is
    # simply not present in the payload at all — not answered wrong, not
    # left blank, just absent.
    only_answer = [{"question_id": qs[0]["id"], "selected_option_ids": [qs[0]["options"][0]["id"]]}]
    submitted = await client.post(
        f"/contests/attempts/{start.json()['attempt_id']}/submit", json={"answers": only_answer}, headers=student,
    )
    assert submitted.status_code == 200, submitted.text
    result = submitted.json()

    # The exploit this regression-tests: with the bug, points_possible would
    # equal only the first question's points (the one answered), producing
    # a 100% score regardless of how many questions were actually skipped.
    assert result["score_percent"] < 100, result
    assert result["points_possible"] > result["points_earned"], result
