"""Proves the double-submit race fix actually closes the race, rather than
just asserting the code looks right.

app/api/v1/quizzes.py::submit_attempt and app/api/v1/exams.py::submit_exam_attempt
both fetch the attempt with `with_for_update=True` specifically so concurrent
submits for the same attempt serialize against each other at the database
level instead of racing to read status=="in_progress" before either commits.
Without that lock, N concurrent submits could each independently grade and
award points — this test fires real concurrent requests through the actual
ASGI app (not a unit test of the locking code in isolation) and checks the
points ledger only reflects one successful grading pass no matter how many
requests raced for the same attempt.
"""
from __future__ import annotations

import asyncio

import pytest

from tests.conftest import auth_headers, grant_role, login

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _make_instructor(client):
    email, headers = await auth_headers(client)
    await grant_role(email, "INSTRUCTOR")
    tokens = await login(client, email)
    return email, {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_concurrent_quiz_submits_award_points_exactly_once(client):
    _, instructor_headers = await _make_instructor(client)
    course_id = (await client.post("/courses", json={
        "title": "Race Course", "slug": "race-course-1",
    }, headers=instructor_headers)).json()["id"]
    question_id = (await client.post("/questions", json={
        "course_id": course_id, "prompt": "2 + 2 = ?", "question_type": "single", "points": 1,
        "options": [
            {"text": "4", "is_correct": True, "order_index": 0},
            {"text": "5", "is_correct": False, "order_index": 1},
        ],
    }, headers=instructor_headers)).json()["id"]
    quiz_id = (await client.post("/quizzes", json={
        "course_id": course_id, "title": "Race Quiz", "max_attempts": 3,
        "pass_score_percent": 50, "question_ids": [question_id],
    }, headers=instructor_headers)).json()["id"]
    await client.post(f"/quizzes/{quiz_id}/publish", headers=instructor_headers)

    _, student_headers = await auth_headers(client)
    questions = (await client.post(f"/quizzes/{quiz_id}/attempts", headers=student_headers)).json()
    correct_option_id = next(o["id"] for o in questions[0]["options"] if o["text"] == "4")
    attempt_id = (await client.get(f"/quizzes/{quiz_id}/attempts/current", headers=student_headers)).json()["attempt_id"]

    payload = {"answers": [{"question_id": question_id, "selected_option_ids": [correct_option_id]}]}

    # Fire many concurrent submits for the exact same attempt_id. Without the
    # row lock in submit_attempt, several of these could all read
    # status == "in_progress" before any of them commits, and each one would
    # independently grade and award points — this is the exact scenario a
    # double-click, a client-side retry, or two open tabs would produce.
    concurrency = 8
    responses = await asyncio.gather(*[
        client.post(f"/quizzes/attempts/{attempt_id}/submit", json=payload, headers=student_headers)
        for _ in range(concurrency)
    ])
    for r in responses:
        assert r.status_code == 200, r.text

    # Every response must report the same final result: one request did the
    # real grading, every other one observed "already submitted" (after
    # blocking on the row lock) and returned that same stored result.
    score_percents = {r.json()["score_percent"] for r in responses}
    assert score_percents == {100}, "concurrent submits disagreed on the final score — the race was not closed"

    stats = (await client.get("/gamification/me", headers=student_headers)).json()
    # 25 for the quiz pass (POINTS_QUIZ_PASS) + 20 for the perfect_quiz badge
    # (100% triggers it) = 45, awarded exactly once. If the race weren't
    # closed, `concurrency` concurrent grading passes would each award 45,
    # e.g. 360 for 8 concurrent requests — any multiple of 45 above 45 itself
    # means points were double-awarded.
    assert stats["total_points"] == 45, (
        f"expected points awarded exactly once (45), got {stats['total_points']} "
        f"— {stats['total_points'] // 45}x duplication if divisible by 45"
    )
    badge_codes = [b["code"] for b in stats["badges"]]
    assert badge_codes.count("perfect_quiz") == 1, "the perfect_quiz badge was awarded more than once"


async def test_concurrent_exam_submits_award_points_exactly_once(client):
    _, instructor_headers = await _make_instructor(client)
    course_id = (await client.post("/courses", json={
        "title": "Race Exam Course", "slug": "race-exam-course-1",
    }, headers=instructor_headers)).json()["id"]
    question_id = (await client.post("/questions", json={
        "course_id": course_id, "prompt": "3 + 3 = ?", "question_type": "single", "points": 1,
        "options": [
            {"text": "6", "is_correct": True, "order_index": 0},
            {"text": "7", "is_correct": False, "order_index": 1},
        ],
    }, headers=instructor_headers)).json()["id"]
    exam_id = (await client.post("/exams", json={
        "course_id": course_id, "title": "Race Exam", "time_limit_seconds": 3600,
        "max_attempts": 1, "pass_score_percent": 50, "question_ids": [question_id],
    }, headers=instructor_headers)).json()["id"]
    await client.post(f"/exams/{exam_id}/publish", headers=instructor_headers)

    _, student_headers = await auth_headers(client)
    start = (await client.post(f"/exams/{exam_id}/attempts", headers=student_headers)).json()
    attempt_id = start["attempt_id"]

    questions = (await client.get(f"/exams/attempts/{attempt_id}/questions", headers=student_headers)).json()
    correct_option_id = next(o["id"] for o in questions[0]["options"] if o["text"] == "6")
    payload = {"answers": [{"question_id": question_id, "selected_option_ids": [correct_option_id]}]}

    concurrency = 8
    responses = await asyncio.gather(*[
        client.post(f"/exams/attempts/{attempt_id}/submit", json=payload, headers=student_headers)
        for _ in range(concurrency)
    ])
    for r in responses:
        assert r.status_code == 200, r.text

    score_percents = {r.json()["score_percent"] for r in responses}
    assert score_percents == {100}, "concurrent exam submits disagreed on the final score — the race was not closed"

    stats = (await client.get("/gamification/me", headers=student_headers)).json()
    # 100 for POINTS_EXAM_PASS — this exam question set doesn't trigger any
    # badge (perfect_quiz only fires on the "quiz_pass" event, not "exam_pass"),
    # so unlike the quiz test above the expected total is just the raw pass award.
    assert stats["total_points"] == 100, (
        f"expected exam-pass points awarded exactly once (100), got {stats['total_points']}"
    )
