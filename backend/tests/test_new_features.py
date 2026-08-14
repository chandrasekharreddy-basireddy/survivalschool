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


async def _make_course(client, instructor_headers, title, slug, publish=True):
    course_id = (await client.post("/courses", json={"title": title, "slug": slug}, headers=instructor_headers)).json()["id"]
    if publish:
        await client.post(f"/courses/{course_id}/publish", headers=instructor_headers)
    return course_id


async def _make_question(client, instructor_headers, course_id, prompt, correct_text, wrong_text):
    resp = await client.post("/questions", json={
        "course_id": course_id, "prompt": prompt, "question_type": "single", "points": 1,
        "options": [{"text": correct_text, "is_correct": True, "order_index": 0},
                    {"text": wrong_text, "is_correct": False, "order_index": 1}],
    }, headers=instructor_headers)
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Timetable
# ---------------------------------------------------------------------------

async def test_timetable_conflict_detection_same_instructor(client):
    _, instructor = await _make_instructor(client)
    course_a = await _make_course(client, instructor, "TT Course A", "tt-course-a")
    course_b = await _make_course(client, instructor, "TT Course B", "tt-course-b")

    first = await client.post("/timetable", json={
        "course_id": course_a, "term": "2026-Fall", "term_start_date": "2026-08-24", "term_end_date": "2026-12-12",
        "day_of_week": 0, "start_time": "09:00:00", "end_time": "10:00:00", "room": "Room 101",
    }, headers=instructor)
    assert first.status_code == 201, first.text

    # Same instructor, overlapping time on the same day/term, DIFFERENT room —
    # still a conflict because the instructor can't teach two classes at once.
    clash = await client.post("/timetable", json={
        "course_id": course_b, "term": "2026-Fall", "term_start_date": "2026-08-24", "term_end_date": "2026-12-12",
        "day_of_week": 0, "start_time": "09:30:00", "end_time": "10:30:00", "room": "Room 202",
    }, headers=instructor)
    assert clash.status_code == 409, clash.text

    # Non-overlapping time on the same day is fine.
    ok = await client.post("/timetable", json={
        "course_id": course_b, "term": "2026-Fall", "term_start_date": "2026-08-24", "term_end_date": "2026-12-12",
        "day_of_week": 0, "start_time": "11:00:00", "end_time": "12:00:00", "room": "Room 202",
    }, headers=instructor)
    assert ok.status_code == 201, ok.text


async def test_timetable_conflict_detection_same_room_different_instructor(client):
    _, instructor_a = await _make_instructor(client)
    _, instructor_b = await _make_instructor(client)
    course_a = await _make_course(client, instructor_a, "Room Course A", "room-course-a")
    course_b = await _make_course(client, instructor_b, "Room Course B", "room-course-b")

    first = await client.post("/timetable", json={
        "course_id": course_a, "term": "2026-Fall", "term_start_date": "2026-08-24", "term_end_date": "2026-12-12",
        "day_of_week": 1, "start_time": "14:00:00", "end_time": "15:00:00", "room": "Lab 1",
    }, headers=instructor_a)
    assert first.status_code == 201

    # Different instructor, but the SAME physical room at an overlapping time —
    # still a real-world conflict (two classes can't share one room).
    clash = await client.post("/timetable", json={
        "course_id": course_b, "term": "2026-Fall", "term_start_date": "2026-08-24", "term_end_date": "2026-12-12",
        "day_of_week": 1, "start_time": "14:30:00", "end_time": "15:30:00", "room": "Lab 1",
    }, headers=instructor_b)
    assert clash.status_code == 409, clash.text


async def test_timetable_non_owner_instructor_forbidden(client):
    _, instructor_a = await _make_instructor(client)
    _, instructor_b = await _make_instructor(client)
    course_a = await _make_course(client, instructor_a, "Owned Course", "owned-course-tt")

    resp = await client.post("/timetable", json={
        "course_id": course_a, "term": "2026-Fall", "term_start_date": "2026-08-24", "term_end_date": "2026-12-12",
        "day_of_week": 2, "start_time": "09:00:00", "end_time": "10:00:00", "room": "R1",
    }, headers=instructor_b)
    assert resp.status_code == 403


async def test_student_personal_timetable_and_ics_export(client):
    _, instructor = await _make_instructor(client)
    enrolled_course = await _make_course(client, instructor, "Enrolled TT Course", "enrolled-tt-course")
    other_course = await _make_course(client, instructor, "Other TT Course", "other-tt-course")

    await client.post("/timetable", json={
        "course_id": enrolled_course, "term": "2026-Fall", "term_start_date": "2026-08-24", "term_end_date": "2026-12-12",
        "day_of_week": 0, "start_time": "09:00:00", "end_time": "10:00:00", "room": "R1",
    }, headers=instructor)
    await client.post("/timetable", json={
        "course_id": other_course, "term": "2026-Fall", "term_start_date": "2026-08-24", "term_end_date": "2026-12-12",
        "day_of_week": 1, "start_time": "09:00:00", "end_time": "10:00:00", "room": "R2",
    }, headers=instructor)

    _, student = await auth_headers(client)
    await client.post(f"/courses/{enrolled_course}/enroll", headers=student)

    mine = await client.get("/timetable/me", params={"term": "2026-Fall"}, headers=student)
    assert mine.status_code == 200
    course_ids = [e["course_id"] for e in mine.json()]
    assert enrolled_course in course_ids
    assert other_course not in course_ids

    ics = await client.get("/timetable/me/export.ics", params={"term": "2026-Fall"}, headers=student)
    assert ics.status_code == 200
    assert ics.headers["content-type"].startswith("text/calendar")
    body = ics.text
    assert "BEGIN:VCALENDAR" in body and "BEGIN:VEVENT" in body and "RRULE:FREQ=WEEKLY" in body


# ---------------------------------------------------------------------------
# Discussions
# ---------------------------------------------------------------------------

async def test_discussion_requires_enrollment_to_post(client):
    _, instructor = await _make_instructor(client)
    course_id = await _make_course(client, instructor, "Disc Course", "disc-course-1")

    _, outsider = await auth_headers(client)
    forbidden = await client.post(f"/courses/{course_id}/discussions", json={"title": "Question", "body": "Help?"}, headers=outsider)
    assert forbidden.status_code == 403

    await client.post(f"/courses/{course_id}/enroll", headers=outsider)
    allowed = await client.post(f"/courses/{course_id}/discussions", json={"title": "Question", "body": "Help?"}, headers=outsider)
    assert allowed.status_code == 201, allowed.text


async def test_discussion_reply_marks_instructor_answer_and_resolve_permission(client):
    _, instructor = await _make_instructor(client)
    course_id = await _make_course(client, instructor, "Resolve Course", "resolve-course-1")
    _, student = await auth_headers(client)
    await client.post(f"/courses/{course_id}/enroll", headers=student)

    thread_id = (await client.post(f"/courses/{course_id}/discussions", json={
        "title": "How does grading work?", "body": "Is it server-side?",
    }, headers=student)).json()["id"]

    student_reply = (await client.post(f"/discussions/{thread_id}/replies", json={"body": "Bumping this."}, headers=student)).json()
    assert student_reply["is_instructor_answer"] is False

    instructor_reply = (await client.post(f"/discussions/{thread_id}/replies", json={"body": "Yes, fully server-side."}, headers=instructor)).json()
    assert instructor_reply["is_instructor_answer"] is True

    forbidden = await client.post(f"/discussions/{thread_id}/resolve", headers=student)
    assert forbidden.status_code == 403

    resolved = await client.post(f"/discussions/{thread_id}/resolve", headers=instructor)
    assert resolved.status_code == 200
    assert resolved.json()["is_resolved"] is True


async def test_discussion_upvote_is_a_toggle_per_user(client):
    _, instructor = await _make_instructor(client)
    course_id = await _make_course(client, instructor, "Upvote Course", "upvote-course-1")
    _, student = await auth_headers(client)
    await client.post(f"/courses/{course_id}/enroll", headers=student)
    thread_id = (await client.post(f"/courses/{course_id}/discussions", json={
        "title": "Upvote me", "body": "body text",
    }, headers=student)).json()["id"]

    up1 = (await client.post(f"/discussions/{thread_id}/upvote", headers=student)).json()
    assert up1["upvote_count"] == 1 and up1["has_voted"] is True

    down = (await client.post(f"/discussions/{thread_id}/upvote", headers=student)).json()
    assert down["upvote_count"] == 0 and down["has_voted"] is False


async def test_unpublished_course_discussions_hidden_from_others(client):
    _, instructor_a = await _make_instructor(client)
    _, instructor_b = await _make_instructor(client)
    course_id = await _make_course(client, instructor_a, "Private Draft Course", "private-draft-disc", publish=False)

    anon = await client.get(f"/courses/{course_id}/discussions")
    assert anon.status_code == 401

    other = await client.get(f"/courses/{course_id}/discussions", headers=instructor_b)
    assert other.status_code == 403

    owner = await client.get(f"/courses/{course_id}/discussions", headers=instructor_a)
    assert owner.status_code == 200


# ---------------------------------------------------------------------------
# Practice mode + bookmarks
# ---------------------------------------------------------------------------

async def test_bookmark_and_practice_from_bookmarks(client):
    _, instructor = await _make_instructor(client)
    course_id = await _make_course(client, instructor, "Bookmark Course", "bookmark-course-1")
    question_id = await _make_question(client, instructor, course_id, "2+2?", "4", "5")

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


async def test_practice_from_mistakes_uses_real_wrong_answers(client):
    _, instructor = await _make_instructor(client)
    course_id = await _make_course(client, instructor, "Mistakes Course", "mistakes-course-1")
    question_id = await _make_question(client, instructor, course_id, "Capital of Japan?", "Tokyo", "Osaka")
    quiz_id = (await client.post("/quizzes", json={"course_id": course_id, "title": "MQ", "question_ids": [question_id]}, headers=instructor)).json()["id"]
    await client.post(f"/quizzes/{quiz_id}/publish", headers=instructor)

    _, student = await auth_headers(client)
    questions = (await client.post(f"/quizzes/{quiz_id}/attempts", headers=student)).json()
    wrong_option = next(o["id"] for o in questions[0]["options"] if o["text"] == "Osaka")
    attempt_id = (await client.get(f"/quizzes/{quiz_id}/attempts/current", headers=student)).json()["attempt_id"]
    await client.post(f"/quizzes/attempts/{attempt_id}/submit", json={
        "answers": [{"question_id": question_id, "selected_option_ids": [wrong_option]}],
    }, headers=student)

    # No mistakes yet for a DIFFERENT, unrelated student.
    _, other_student = await auth_headers(client)
    empty = await client.post("/practice/sessions", json={"source": "mistakes", "limit": 5}, headers=other_student)
    assert empty.status_code == 404

    started = await client.post("/practice/sessions", json={"source": "mistakes", "limit": 5}, headers=student)
    assert started.status_code == 201
    assert started.json()["questions"][0]["id"] == question_id


async def test_practice_grading_ignores_client_submitted_correctness_and_awards_no_points(client):
    """Anti-cheat parity with quizzes/exams (spec: never trust a client-submitted
    score), PLUS practice mode's own deliberate design constraint: it never
    awards gamification points, so bookmarking+re-practicing a question can't
    be used to farm points the way a real quiz/exam pass can."""
    _, instructor = await _make_instructor(client)
    course_id = await _make_course(client, instructor, "Anticheat Practice Course", "anticheat-practice-course")
    question_id = await _make_question(client, instructor, course_id, "1+1?", "2", "3")

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


# ---------------------------------------------------------------------------
# Instructor analytics
# ---------------------------------------------------------------------------

async def test_course_analytics_access_restricted_to_owner_or_admin(client):
    _, instructor_a = await _make_instructor(client)
    _, instructor_b = await _make_instructor(client)
    course_id = await _make_course(client, instructor_a, "Analytics Course", "analytics-course-1")

    forbidden = await client.get(f"/courses/{course_id}/analytics/overview", headers=instructor_b)
    assert forbidden.status_code == 403

    owner = await client.get(f"/courses/{course_id}/analytics/overview", headers=instructor_a)
    assert owner.status_code == 200

    _, admin = await _make_admin(client)
    admin_view = await client.get(f"/courses/{course_id}/analytics/overview", headers=admin)
    assert admin_view.status_code == 200


async def test_course_analytics_reflects_real_answer_data(client):
    _, instructor = await _make_instructor(client)
    course_id = await _make_course(client, instructor, "Real Data Course", "real-data-course-1")
    q1 = await _make_question(client, instructor, course_id, "Q1?", "Right1", "Wrong1")
    q2 = await _make_question(client, instructor, course_id, "Q2?", "Right2", "Wrong2")
    quiz_id = (await client.post("/quizzes", json={"course_id": course_id, "title": "AQ", "question_ids": [q1, q2]}, headers=instructor)).json()["id"]
    await client.post(f"/quizzes/{quiz_id}/publish", headers=instructor)
    await client.post(f"/courses/{course_id}/publish", headers=instructor)

    # Student 1: gets both right. Student 2: gets q1 wrong, q2 right.
    for get_q1_right in (True, False):
        _, s = await auth_headers(client)
        await client.post(f"/courses/{course_id}/enroll", headers=s)
        questions = (await client.post(f"/quizzes/{quiz_id}/attempts", headers=s)).json()
        opts = {q["id"]: {o["text"]: o["id"] for o in q["options"]} for q in questions}
        attempt_id = (await client.get(f"/quizzes/{quiz_id}/attempts/current", headers=s)).json()["attempt_id"]
        q1_choice = opts[q1]["Right1"] if get_q1_right else opts[q1]["Wrong1"]
        await client.post(f"/quizzes/attempts/{attempt_id}/submit", json={
            "answers": [
                {"question_id": q1, "selected_option_ids": [q1_choice]},
                {"question_id": q2, "selected_option_ids": [opts[q2]["Right2"]]},
            ],
        }, headers=s)

    stats = {row["question_id"]: row for row in (await client.get(f"/courses/{course_id}/analytics/questions", headers=instructor)).json()}
    assert stats[q1]["times_answered"] == 2
    assert stats[q1]["times_correct"] == 1
    assert stats[q1]["percent_correct"] == 50.0
    assert stats[q2]["times_correct"] == 2
    assert stats[q2]["percent_correct"] == 100.0

    overview = (await client.get(f"/courses/{course_id}/analytics/overview", headers=instructor)).json()
    assert overview["enrolled_count"] == 2
    assert overview["quiz_attempts_count"] == 2

    csv_resp = await client.get(f"/courses/{course_id}/analytics/export.csv", headers=instructor)
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")
    assert "times_answered" in csv_resp.text
    assert "Q1?" in csv_resp.text


# ---------------------------------------------------------------------------
# Global search
# ---------------------------------------------------------------------------

async def test_search_returns_courses_and_discussions_but_excludes_unpublished(client):
    _, instructor = await _make_instructor(client)
    published = await _make_course(client, instructor, "Zephyr Astronomy Basics", "zephyr-astronomy-basics")
    await _make_course(client, instructor, "Zephyr Secret Draft", "zephyr-secret-draft", publish=False)

    _, student = await auth_headers(client)
    await client.post(f"/courses/{published}/enroll", headers=student)
    await client.post(f"/courses/{published}/discussions", json={
        "title": "Zephyr orbital mechanics question", "body": "How does this work?",
    }, headers=student)

    resp = await client.get("/search", params={"q": "Zephyr"})
    assert resp.status_code == 200
    results = resp.json()["results"]
    titles = [r["title"] for r in results]
    types = {r["type"] for r in results}
    assert "Zephyr Astronomy Basics" in titles
    assert "Zephyr orbital mechanics question" in titles
    assert "Zephyr Secret Draft" not in titles
    assert "course" in types and "discussion" in types

    too_short = await client.get("/search", params={"q": "Z"})
    assert too_short.status_code == 422
