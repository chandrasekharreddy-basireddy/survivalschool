from __future__ import annotations

from tests.conftest import auth_headers, grant_role, login

pytestmark = __import__("pytest").mark.asyncio(loop_scope="session")


async def _make_instructor(client):
    email, headers = await auth_headers(client)
    await grant_role(email, "INSTRUCTOR")
    tokens = await login(client, email)
    return email, {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_quiz_scoring_ignores_client_submitted_correctness(client):
    _, instructor_headers = await _make_instructor(client)

    course_resp = await client.post("/courses", json={
        "title": "Cheat-Proof Course", "slug": "cheat-proof-course-1",
    }, headers=instructor_headers)
    course_id = course_resp.json()["id"]

    question_resp = await client.post("/questions", json={
        "course_id": course_id,
        "prompt": "2 + 2 = ?",
        "question_type": "single",
        "points": 1,
        "options": [
            {"text": "3", "is_correct": False, "order_index": 0},
            {"text": "4", "is_correct": True, "order_index": 1},
        ],
    }, headers=instructor_headers)
    question = question_resp.json()
    question_id = question["id"]

    quiz_resp = await client.post("/quizzes", json={
        "course_id": course_id, "title": "Math Quiz", "max_attempts": 3,
        "pass_score_percent": 70, "question_ids": [question_id],
    }, headers=instructor_headers)
    quiz_id = quiz_resp.json()["id"]
    await client.post(f"/quizzes/{quiz_id}/publish", headers=instructor_headers)

    _, student_headers = await auth_headers(client)
    questions = (await client.post(f"/quizzes/{quiz_id}/attempts", headers=student_headers)).json()
    options = questions[0]["options"]
    wrong_option_id = next(o["id"] for o in options if o["text"] == "3")

    # Sanity: correctness is never leaked to the client before submission.
    assert all("is_correct" not in o for o in options)

    current = (await client.get(f"/quizzes/{quiz_id}/attempts/current", headers=student_headers)).json()
    attempt_id = current["attempt_id"]

    submit_resp = await client.post(f"/quizzes/attempts/{attempt_id}/submit", json={
        "answers": [{
            "question_id": question_id, "selected_option_ids": [wrong_option_id],
            # An attacker-controlled client could send these — the server must ignore them.
            "is_correct": True, "score_percent": 100,
        }],
    }, headers=student_headers)
    result = submit_resp.json()

    assert result["score_percent"] == 0
    assert result["passed"] is False
    assert result["points_earned"] == 0


async def test_duplicate_quiz_submission_is_idempotent(client):
    _, instructor_headers = await _make_instructor(client)
    course_id = (await client.post("/courses", json={"title": "Idempotency Course", "slug": "idempotency-course-1"}, headers=instructor_headers)).json()["id"]
    question_id = (await client.post("/questions", json={
        "course_id": course_id, "prompt": "True or false: sky is blue", "question_type": "true_false", "points": 1,
        "options": [{"text": "True", "is_correct": True, "order_index": 0}, {"text": "False", "is_correct": False, "order_index": 1}],
    }, headers=instructor_headers)).json()["id"]
    quiz_id = (await client.post("/quizzes", json={
        "course_id": course_id, "title": "TF Quiz", "max_attempts": 3, "pass_score_percent": 70, "question_ids": [question_id],
    }, headers=instructor_headers)).json()["id"]
    await client.post(f"/quizzes/{quiz_id}/publish", headers=instructor_headers)

    _, student_headers = await auth_headers(client)
    await client.post(f"/quizzes/{quiz_id}/attempts", headers=student_headers)
    attempt_id = (await client.get(f"/quizzes/{quiz_id}/attempts/current", headers=student_headers)).json()["attempt_id"]

    first = await client.post(f"/quizzes/attempts/{attempt_id}/submit", json={"answers": []}, headers=student_headers)
    second = await client.post(f"/quizzes/attempts/{attempt_id}/submit", json={"answers": []}, headers=student_headers)
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["score_percent"] == second.json()["score_percent"]


async def test_course_completion_issues_verifiable_certificate(client):
    _, instructor_headers = await _make_instructor(client)
    course_resp = await client.post("/courses", json={"title": "Cert Course", "slug": "cert-course-1"}, headers=instructor_headers)
    course_id = course_resp.json()["id"]
    await client.post(f"/courses/{course_id}/publish", headers=instructor_headers)

    # Seeded directly through the ORM here purely to keep this test focused on
    # the completion/certificate path (POST /courses/{id}/sections and
    # POST /lessons/sections/{id} exercise section/lesson creation elsewhere).
    from app.database import AsyncSessionLocal
    from app.models.lms import CourseSection, Lesson

    async with AsyncSessionLocal() as db:
        section = CourseSection(course_id=course_id, title="Only Section", order_index=0)
        db.add(section)
        await db.flush()
        lesson = Lesson(section_id=section.id, title="Only Lesson", content_body="content", order_index=0)
        db.add(lesson)
        await db.commit()
        await db.refresh(lesson)
        lesson_id = str(lesson.id)

    _, student_headers = await auth_headers(client)
    await client.post(f"/courses/{course_id}/enroll", headers=student_headers)

    certs_before = (await client.get("/certificates/me", headers=student_headers)).json()
    assert certs_before == []

    complete_resp = await client.post(f"/lessons/{lesson_id}/complete", headers=student_headers)
    assert complete_resp.status_code == 200

    certs_after = (await client.get("/certificates/me", headers=student_headers)).json()
    assert len(certs_after) == 1
    cert_number = certs_after[0]["certificate_number"]

    public = await client.get(f"/certificates/verify/{cert_number}")
    assert public.status_code == 200
    body = public.json()
    assert body["valid"] is True
    assert body["course_title"] == "Cert Course"
    # PII minimization: only first name is exposed publicly, never email.
    assert "email" not in body

    bogus = await client.get("/certificates/verify/SS-DOES-NOT-EXIST")
    assert bogus.json()["valid"] is False


async def test_gamification_points_and_badges_are_server_computed(client):
    _, instructor_headers = await _make_instructor(client)
    course_id = (await client.post("/courses", json={"title": "Points Course", "slug": "points-course-1"}, headers=instructor_headers)).json()["id"]
    await client.post(f"/courses/{course_id}/publish", headers=instructor_headers)

    from app.database import AsyncSessionLocal
    from app.models.lms import CourseSection, Lesson

    async with AsyncSessionLocal() as db:
        section = CourseSection(course_id=course_id, title="S", order_index=0)
        db.add(section)
        await db.flush()
        lesson = Lesson(section_id=section.id, title="L", content_body="c", order_index=0)
        db.add(lesson)
        await db.commit()
        await db.refresh(lesson)
        lesson_id = str(lesson.id)

    _, student_headers = await auth_headers(client)
    await client.post(f"/courses/{course_id}/enroll", headers=student_headers)

    before = (await client.get("/gamification/me", headers=student_headers)).json()
    assert before["total_points"] == 0

    await client.post(f"/lessons/{lesson_id}/complete", headers=student_headers)

    after = (await client.get("/gamification/me", headers=student_headers)).json()
    # 10 for the lesson + 20 for the first_lesson badge + 150 for course completion
    # (single-lesson course) + 20 for the course_finisher badge = 200.
    assert after["total_points"] == 200
    badge_codes = {b["code"] for b in after["badges"]}
    assert {"first_lesson", "course_finisher"}.issubset(badge_codes)
