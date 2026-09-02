from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

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


async def _seed_subject_and_topic(client, admin_headers):
    unique = uuid.uuid4().hex[:8]
    subject_id = (await client.post("/subjects", json={"name": f"Subject {unique}", "slug": f"subj-{unique}"}, headers=admin_headers)).json()["id"]
    topic_id = (await client.post(f"/subjects/{subject_id}/topics", json={"name": f"Topic {unique}", "slug": f"topic-{unique}"}, headers=admin_headers)).json()["id"]
    return subject_id, topic_id


async def _make_question(client, instructor_headers, subject_id, topic_id, prompt, correct_text, wrong_text):
    resp = await client.post("/questions", json={
        "subject_id": subject_id, "topic_id": topic_id, "prompt": prompt, "question_type": "single", "points": 1,
        "options": [{"text": correct_text, "is_correct": True, "order_index": 0},
                    {"text": wrong_text, "is_correct": False, "order_index": 1}],
    }, headers=instructor_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Practice mode + bookmarks
# ---------------------------------------------------------------------------

async def test_bookmark_and_practice_from_bookmarks(client):
    _, admin = await _make_admin(client)
    _, instructor = await _make_instructor(client)
    subject_id, topic_id = await _seed_subject_and_topic(client, admin)
    question_id = await _make_question(client, instructor, subject_id, topic_id, "2+2?", "4", "5")

    _, student = await auth_headers(client)
    bookmarked = await client.post(f"/questions/{question_id}/bookmark", json={"note": "review later"}, headers=student)
    assert bookmarked.status_code == 201, bookmarked.text

    listed = (await client.get("/practice/bookmarks", headers=student)).json()
    assert any(b["question_id"] == question_id for b in listed)

    started = await client.post("/practice/sessions", json={"source": "bookmarks", "limit": 5}, headers=student)
    assert started.status_code == 201, started.text
    session = started.json()
    assert len(session["questions"]) == 1
    q = session["questions"][0]
    correct_option = next(o["id"] for o in q["options"] if o["text"] == "4")

    result = await client.post(f"/practice/sessions/{session['id']}/submit", json={
        "answers": [{"question_id": question_id, "selected_option_ids": [correct_option]}],
    }, headers=student)
    assert result.status_code == 200
    body = result.json()
    assert body["score_percent"] == 100
    assert body["answers"][0]["is_correct"] is True
    assert body["answers"][0]["correct_option_ids"] == [correct_option]

    remove = await client.delete(f"/questions/{question_id}/bookmark", headers=student)
    assert remove.status_code == 200
    after = (await client.get("/practice/bookmarks", headers=student)).json()
    assert not any(b["question_id"] == question_id for b in after)


async def test_practice_from_mistakes_uses_real_wrong_answers_from_a_contest(client):
    """practice_service's "mistakes" source now draws on wrong ContestAnswer/
    EliminationAnswer rows instead of the removed QuizAnswer table — this
    exercises the contest half of that (see app/api/v1/practice.py::_mistake_question_ids)."""
    _, admin = await _make_admin(client)
    _, instructor = await _make_instructor(client)
    subject_id, topic_id = await _seed_subject_and_topic(client, admin)
    question_id = await _make_question(client, instructor, subject_id, topic_id, "Capital of Japan?", "Tokyo", "Osaka")

    now = datetime.now(UTC)
    contest_id = (await client.post("/contests", json={
        "title": "Mistakes Source Contest", "starts_at": (now - timedelta(minutes=1)).isoformat(),
        "ends_at": (now + timedelta(hours=1)).isoformat(), "duration_seconds": 3600, "question_ids": [question_id],
    }, headers=admin)).json()["id"]

    _, student = await auth_headers(client)
    start = await client.post(f"/contests/{contest_id}/attempts", headers=student)
    attempt_id = start.json()["attempt_id"]
    qs = (await client.get(f"/contests/attempts/{attempt_id}/questions", headers=student)).json()
    wrong_option = next(o["id"] for o in qs[0]["options"] if o["text"] == "Osaka")
    submitted = await client.post(f"/contests/attempts/{attempt_id}/submit", json={
        "answers": [{"question_id": question_id, "selected_option_ids": [wrong_option]}],
    }, headers=student)
    assert submitted.status_code == 200, submitted.text

    # No mistakes yet for a DIFFERENT, unrelated student.
    _, other_student = await auth_headers(client)
    empty = await client.post("/practice/sessions", json={"source": "mistakes", "limit": 5}, headers=other_student)
    assert empty.status_code == 404

    started = await client.post("/practice/sessions", json={"source": "mistakes", "limit": 5}, headers=student)
    assert started.status_code == 201, started.text
    assert started.json()["questions"][0]["id"] == question_id


async def test_practice_grading_ignores_client_submitted_correctness_and_awards_no_points(client):
    """Anti-cheat parity with contests/elimination battles (never trust a
    client-submitted score), PLUS practice mode's own deliberate design
    constraint: it never awards gamification points, so bookmarking+re-practicing
    a question can't be used to farm points the way a real contest pass can."""
    _, admin = await _make_admin(client)
    _, instructor = await _make_instructor(client)
    subject_id, topic_id = await _seed_subject_and_topic(client, admin)
    question_id = await _make_question(client, instructor, subject_id, topic_id, "1+1?", "2", "3")

    _, student = await auth_headers(client)
    before_points = (await client.get("/gamification/me", headers=student)).json()["total_points"]

    await client.post(f"/questions/{question_id}/bookmark", json={}, headers=student)
    session = (await client.post("/practice/sessions", json={"source": "bookmarks", "limit": 5}, headers=student)).json()
    wrong_option = next(o["id"] for o in session["questions"][0]["options"] if o["text"] == "3")

    # Client claims is_correct implicitly by picking the wrong option but the
    # server must grade independently — selecting the wrong option must not
    # score as correct no matter what.
    result = (await client.post(f"/practice/sessions/{session['id']}/submit", json={
        "answers": [{"question_id": question_id, "selected_option_ids": [wrong_option]}],
    }, headers=student)).json()
    assert result["score_percent"] == 0
    assert result["answers"][0]["is_correct"] is False

    after_points = (await client.get("/gamification/me", headers=student)).json()["total_points"]
    assert after_points == before_points


async def test_practice_submitting_a_partial_answer_set_does_not_inflate_the_score(client):
    """Regression test for a real scoring-integrity bug (the same one fixed
    in contests.py's submit_contest_attempt): submit_practice_session used
    to compute points_possible only from the questions present in
    payload.answers, which has no completeness requirement. A student could
    get a perfect score_percent by simply omitting every question they
    weren't confident about from the payload entirely, since the "possible
    points" denominator shrank to match whatever they chose to answer.
    Answering exactly one of two bookmarked questions correctly, and
    omitting the other from the payload, must score 50%, not 100%."""
    _, admin = await _make_admin(client)
    _, instructor = await _make_instructor(client)
    subject_id, topic_id = await _seed_subject_and_topic(client, admin)
    q1 = await _make_question(client, instructor, subject_id, topic_id, "2+2?", "4", "5")
    q2 = await _make_question(client, instructor, subject_id, topic_id, "3+3?", "6", "7")

    _, student = await auth_headers(client)
    await client.post(f"/questions/{q1}/bookmark", json={}, headers=student)
    await client.post(f"/questions/{q2}/bookmark", json={}, headers=student)

    session = (await client.post("/practice/sessions", json={"source": "bookmarks", "limit": 5}, headers=student)).json()
    assert len(session["questions"]) == 2

    q1_out = next(q for q in session["questions"] if q["id"] == q1)
    correct_option = next(o["id"] for o in q1_out["options"] if o["text"] == "4")

    # Answer only q1, correctly. q2 is not present in the payload at all —
    # not answered wrong, not left blank, just absent.
    result = (await client.post(f"/practice/sessions/{session['id']}/submit", json={
        "answers": [{"question_id": q1, "selected_option_ids": [correct_option]}],
    }, headers=student)).json()

    # The exploit this regression-tests: with the bug, points_possible would
    # equal only q1's points (the one answered), producing a 100% score
    # regardless of q2 being skipped entirely. The fix grades every question
    # in the session's fixed question_order, so "answers" now includes q2
    # too (unanswered, graded as incorrect) — look it up by id rather than
    # assuming array order, since question_order isn't submission order.
    assert result["score_percent"] == 50, result
    assert result["points_possible"] == 2, result
    assert result["points_earned"] == 1, result
    answers_by_qid = {a["question_id"]: a for a in result["answers"]}
    assert answers_by_qid[q1]["is_correct"] is True
    assert answers_by_qid[q2]["is_correct"] is False
    assert answers_by_qid[q2]["selected_option_ids"] == []
