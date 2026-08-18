from __future__ import annotations

import io
import tempfile
from unittest.mock import patch

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


async def _complete_single_lesson_course(client, instructor_headers, course_id):
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
        return str(lesson.id)


async def test_course_quizzes_and_exams_listing_endpoints(client):
    _, instructor_headers = await _make_instructor(client)
    course_id = (await client.post("/courses", json={
        "title": "Listing Course", "slug": "listing-course-1",
        "skills": ["Python", "SQL"], "specialization": "Backend Engineering",
    }, headers=instructor_headers)).json()["id"]

    question_id = (await client.post("/questions", json={
        "course_id": course_id, "prompt": "1+1?", "question_type": "single", "points": 1,
        "options": [{"text": "2", "is_correct": True, "order_index": 0}, {"text": "3", "is_correct": False, "order_index": 1}],
    }, headers=instructor_headers)).json()["id"]

    quiz_id = (await client.post("/quizzes", json={
        "course_id": course_id, "title": "Q1", "question_ids": [question_id],
    }, headers=instructor_headers)).json()["id"]
    await client.post(f"/quizzes/{quiz_id}/publish", headers=instructor_headers)

    exam_id = (await client.post("/exams", json={
        "course_id": course_id, "title": "Final Exam", "question_ids": [question_id],
    }, headers=instructor_headers)).json()["id"]
    await client.post(f"/exams/{exam_id}/publish", headers=instructor_headers)

    quizzes = (await client.get(f"/courses/{course_id}/quizzes")).json()
    exams = (await client.get(f"/courses/{course_id}/exams")).json()
    assert [q["id"] for q in quizzes] == [quiz_id]
    assert [e["id"] for e in exams] == [exam_id]

    course = (await client.get(f"/courses/{course_id}")).json()
    assert course["skills"] == ["Python", "SQL"]
    assert course["specialization"] == "Backend Engineering"


async def test_courses_list_is_paginated_with_total_count_header(client):
    _, instructor_headers = await _make_instructor(client)
    for i in range(3):
        cid = (await client.post("/courses", json={"title": f"Page Course {i}", "slug": f"page-course-{i}"}, headers=instructor_headers)).json()["id"]
        await client.post(f"/courses/{cid}/publish", headers=instructor_headers)

    resp = await client.get("/courses", params={"limit": 2, "offset": 0})
    assert resp.status_code == 200
    assert len(resp.json()) <= 2
    assert int(resp.headers["x-total-count"]) >= 3


async def test_quiz_and_exam_attempt_history_endpoints(client):
    _, instructor_headers = await _make_instructor(client)
    course_id = (await client.post("/courses", json={"title": "History Course", "slug": "history-course-1"}, headers=instructor_headers)).json()["id"]
    question_id = (await client.post("/questions", json={
        "course_id": course_id, "prompt": "2+2?", "question_type": "single", "points": 1,
        "options": [{"text": "4", "is_correct": True, "order_index": 0}, {"text": "5", "is_correct": False, "order_index": 1}],
    }, headers=instructor_headers)).json()["id"]
    quiz_id = (await client.post("/quizzes", json={"course_id": course_id, "title": "HQ", "question_ids": [question_id]}, headers=instructor_headers)).json()["id"]
    await client.post(f"/quizzes/{quiz_id}/publish", headers=instructor_headers)
    exam_id = (await client.post("/exams", json={"course_id": course_id, "title": "HE", "question_ids": [question_id]}, headers=instructor_headers)).json()["id"]
    await client.post(f"/exams/{exam_id}/publish", headers=instructor_headers)

    _, student_headers = await auth_headers(client)

    await client.post(f"/quizzes/{quiz_id}/attempts", headers=student_headers)
    quiz_attempt_id = (await client.get(f"/quizzes/{quiz_id}/attempts/current", headers=student_headers)).json()["attempt_id"]
    await client.post(f"/quizzes/attempts/{quiz_attempt_id}/submit", json={"answers": []}, headers=student_headers)

    exam_start = (await client.post(f"/exams/{exam_id}/attempts", headers=student_headers)).json()
    exam_attempt_id = exam_start["attempt_id"]
    await client.post(f"/exams/attempts/{exam_attempt_id}/submit", json={"answers": []}, headers=student_headers)

    quiz_history = (await client.get("/quizzes/me/attempts", headers=student_headers)).json()
    exam_history = (await client.get("/exams/me/attempts", headers=student_headers)).json()
    assert len(quiz_history) == 1 and quiz_history[0]["title"] == "HQ"
    assert len(exam_history) == 1 and exam_history[0]["title"] == "HE"


async def test_exam_review_endpoint_shows_correct_answers_only_after_submit(client):
    _, instructor_headers = await _make_instructor(client)
    course_id = (await client.post("/courses", json={"title": "Review Course", "slug": "review-course-1"}, headers=instructor_headers)).json()["id"]
    question_id = (await client.post("/questions", json={
        "course_id": course_id, "prompt": "Capital of France?", "question_type": "single", "points": 1,
        "options": [{"text": "Paris", "is_correct": True, "order_index": 0}, {"text": "Berlin", "is_correct": False, "order_index": 1}],
    }, headers=instructor_headers)).json()["id"]
    exam_id = (await client.post("/exams", json={"course_id": course_id, "title": "RE", "question_ids": [question_id]}, headers=instructor_headers)).json()["id"]
    await client.post(f"/exams/{exam_id}/publish", headers=instructor_headers)

    _, student_headers = await auth_headers(client)
    start = (await client.post(f"/exams/{exam_id}/attempts", headers=student_headers)).json()
    attempt_id = start["attempt_id"]

    # Review before submission is rejected — must not leak correct answers mid-exam.
    early = await client.get(f"/exams/attempts/{attempt_id}/review", headers=student_headers)
    assert early.status_code == 409

    berlin_option_id = None
    questions = (await client.get(f"/exams/attempts/{attempt_id}/questions", headers=student_headers)).json()
    for opt in questions[0]["options"]:
        if opt["text"] == "Berlin":
            berlin_option_id = opt["id"]

    await client.post(f"/exams/attempts/{attempt_id}/submit", json={
        "answers": [{"question_id": question_id, "selected_option_ids": [berlin_option_id]}],
    }, headers=student_headers)

    review = await client.get(f"/exams/attempts/{attempt_id}/review", headers=student_headers)
    assert review.status_code == 200
    body = review.json()
    assert body["answers"][0]["is_correct"] is False
    assert body["answers"][0]["correct_option_ids"] != body["answers"][0]["selected_option_ids"]


async def test_certificate_has_grade_score_skills_and_can_be_revoked(client):
    _, instructor_headers = await _make_instructor(client)
    course_id = (await client.post("/courses", json={
        "title": "Grading Course", "slug": "grading-course-1", "skills": ["Data Structures"],
    }, headers=instructor_headers)).json()["id"]
    await client.post(f"/courses/{course_id}/publish", headers=instructor_headers)

    question_id = (await client.post("/questions", json={
        "course_id": course_id, "prompt": "5*5?", "question_type": "single", "points": 1,
        "options": [{"text": "25", "is_correct": True, "order_index": 0}, {"text": "20", "is_correct": False, "order_index": 1}],
    }, headers=instructor_headers)).json()["id"]
    quiz_id = (await client.post("/quizzes", json={"course_id": course_id, "title": "GQ", "question_ids": [question_id]}, headers=instructor_headers)).json()["id"]
    await client.post(f"/quizzes/{quiz_id}/publish", headers=instructor_headers)

    _, student_headers = await auth_headers(client)
    await client.post(f"/courses/{course_id}/enroll", headers=student_headers)

    correct_option_id = None
    questions = (await client.post(f"/quizzes/{quiz_id}/attempts", headers=student_headers)).json()
    for opt in questions[0]["options"]:
        if opt["text"] == "25":
            correct_option_id = opt["id"]
    attempt_id = (await client.get(f"/quizzes/{quiz_id}/attempts/current", headers=student_headers)).json()["attempt_id"]
    await client.post(f"/quizzes/attempts/{attempt_id}/submit", json={
        "answers": [{"question_id": question_id, "selected_option_ids": [correct_option_id]}],
    }, headers=student_headers)

    lesson_id = await _complete_single_lesson_course(client, instructor_headers, course_id)
    await client.post(f"/lessons/{lesson_id}/complete", headers=student_headers)

    certs = (await client.get("/certificates/me", headers=student_headers)).json()
    assert len(certs) == 1
    cert = certs[0]
    assert cert["score_percent"] == 100
    assert cert["grade"] == "A+"
    assert cert["skills"] == ["Data Structures"]
    cert_number = cert["certificate_number"]

    public_before = (await client.get(f"/certificates/verify/{cert_number}")).json()
    assert public_before["valid"] is True
    assert public_before["student_full_name"]
    assert public_before["grade"] == "A+"

    # A non-admin cannot revoke.
    forbidden = await client.post(f"/certificates/{cert_number}/revoke", headers=student_headers)
    assert forbidden.status_code == 403

    _, admin_headers = await _make_admin(client)
    revoke_resp = await client.post(f"/certificates/{cert_number}/revoke", headers=admin_headers)
    assert revoke_resp.status_code == 200

    public_after = (await client.get(f"/certificates/verify/{cert_number}")).json()
    assert public_after["valid"] is False
    assert public_after["invalid_reason"] == "revoked"

    pdf_resp = await client.get(f"/certificates/{cert_number}/pdf")
    assert pdf_resp.status_code == 404  # revoked certs don't serve a PDF


async def test_certificate_pdf_endpoint_returns_real_pdf_for_valid_certificate(client):
    _, instructor_headers = await _make_instructor(client)
    course_id = (await client.post("/courses", json={"title": "PDF Course", "slug": "pdf-course-1"}, headers=instructor_headers)).json()["id"]
    await client.post(f"/courses/{course_id}/publish", headers=instructor_headers)

    _, student_headers = await auth_headers(client)
    await client.post(f"/courses/{course_id}/enroll", headers=student_headers)
    lesson_id = await _complete_single_lesson_course(client, instructor_headers, course_id)
    await client.post(f"/lessons/{lesson_id}/complete", headers=student_headers)

    cert_number = (await client.get("/certificates/me", headers=student_headers)).json()[0]["certificate_number"]
    pdf_resp = await client.get(f"/certificates/{cert_number}/pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert pdf_resp.content[:4] == b"%PDF"


async def test_admin_user_management_endpoints(client):
    _, admin_headers = await _make_admin(client)
    student_email, student_headers = await auth_headers(client)

    listed = await client.get("/admin/users", params={"q": student_email}, headers=admin_headers)
    assert listed.status_code == 200
    assert any(u["email"] == student_email for u in listed.json())

    target = next(u for u in listed.json() if u["email"] == student_email)
    deactivated = await client.post(f"/admin/users/{target['id']}/deactivate", headers=admin_headers)
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    # A deactivated user can no longer authenticate against protected endpoints.
    blocked = await client.get("/auth/me", headers=student_headers)
    assert blocked.status_code == 401

    reactivated = await client.post(f"/admin/users/{target['id']}/activate", headers=admin_headers)
    assert reactivated.status_code == 200
    assert reactivated.json()["is_active"] is True


async def test_admin_system_health_reports_detail(client):
    _, admin_headers = await _make_admin(client)
    resp = await client.get("/admin/system-health", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["database"] is True
    assert body["redis"] is True
    assert "app_version" in body and "uptime_seconds" in body


async def test_admin_audit_logs_support_filtering(client):
    _, admin_headers = await _make_admin(client)
    resp = await client.get("/admin/audit-logs", params={"action": "user.deactivated", "limit": 5}, headers=admin_headers)
    assert resp.status_code == 200
    for row in resp.json():
        assert row["action"] == "user.deactivated"


async def test_file_upload_rejects_disallowed_type_and_accepts_image(client):
    """Test file upload with mocked storage to avoid /data permission issues."""
    _, headers = await auth_headers(client)

    bad = await client.post(
        "/files", headers=headers,
        files={"file": ("payload.exe", io.BytesIO(b"MZ" + b"\x00" * 50), "application/octet-stream")},
    )
    assert bad.status_code == 422

    # A minimal valid 1x1 PNG.
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    
    # Mock os.makedirs and file writing to use a temp directory instead
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch('app.api.v1.files.settings.STORAGE_LOCAL_PATH', tmpdir):
            with patch('app.api.v1.files.os.makedirs') as mock_makedirs:
                mock_makedirs.return_value = None  # Don't actually try to create /data
                good = await client.post(
                    "/files", headers=headers, params={"visibility": "public"},
                    files={"file": ("avatar.png", io.BytesIO(png_bytes), "image/png")},
                )
    
    assert good.status_code == 201, good.text
    body = good.json()
    assert body["mime_type"] == "image/png"

    download = await client.get(body["url"].replace("/api/v1", ""))
    assert download.status_code == 200
    assert download.content == png_bytes


async def test_private_file_is_not_accessible_to_other_users(client):
    """Test private file access control with mocked storage."""
    _, owner_headers = await auth_headers(client)
    _, other_headers = await auth_headers(client)

    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    
    # Mock os.makedirs to use a temp directory instead of /data
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch('app.api.v1.files.settings.STORAGE_LOCAL_PATH', tmpdir):
            with patch('app.api.v1.files.os.makedirs') as mock_makedirs:
                mock_makedirs.return_value = None  # Don't actually try to create /data
                uploaded = await client.post(
                    "/files", headers=owner_headers, params={"visibility": "private"},
                    files={"file": ("private.png", io.BytesIO(png_bytes), "image/png")},
                )
        file_id = uploaded.json()["id"]

        forbidden = await client.get(f"/files/{file_id}", headers=other_headers)
        assert forbidden.status_code == 403

        anon = await client.get(f"/files/{file_id}")
        assert anon.status_code == 403

        allowed = await client.get(f"/files/{file_id}", headers=owner_headers)
        assert allowed.status_code == 200


async def test_single_quiz_and_exam_metadata_endpoints(client):
    _, instructor_headers = await _make_instructor(client)
    course_id = (await client.post("/courses", json={"title": "Meta Course", "slug": "meta-course-1"}, headers=instructor_headers)).json()["id"]
    quiz_id = (await client.post("/quizzes", json={"course_id": course_id, "title": "Meta Quiz", "max_attempts": 2}, headers=instructor_headers)).json()["id"]
    exam_id = (await client.post("/exams", json={"course_id": course_id, "title": "Meta Exam"}, headers=instructor_headers)).json()["id"]

    quiz_resp = await client.get(f"/quizzes/{quiz_id}")
    assert quiz_resp.status_code == 200
    assert quiz_resp.json()["title"] == "Meta Quiz"
    assert quiz_resp.json()["max_attempts"] == 2

    # Exam metadata (including question_ids) is not public: anonymous callers are
    # rejected, and the managing instructor can still read their own unpublished
    # exam. See the get_exam auth hardening (audit BE-H6).
    anon_exam = await client.get(f"/exams/{exam_id}")
    assert anon_exam.status_code == 401

    exam_resp = await client.get(f"/exams/{exam_id}", headers=instructor_headers)
    assert exam_resp.status_code == 200
    assert exam_resp.json()["title"] == "Meta Exam"

    missing = await client.get("/quizzes/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404


async def test_unpublished_courses_are_not_leaked_to_anonymous_or_other_instructors(client):
    _, instructor_a = await _make_instructor(client)
    _, instructor_b = await _make_instructor(client)
    draft_id = (await client.post("/courses", json={"title": "Secret Draft", "slug": "secret-draft-1"}, headers=instructor_a)).json()["id"]

    anon = await client.get("/courses", params={"published_only": False})
    assert anon.status_code == 401

    other_instructor_view = await client.get("/courses", params={"published_only": False}, headers=instructor_b)
    assert draft_id not in [c["id"] for c in other_instructor_view.json()]

    owner_view = await client.get("/courses", params={"published_only": False}, headers=instructor_a)
    assert draft_id in [c["id"] for c in owner_view.json()]


async def test_leaderboard_returns_ranked_entries_without_error(client):
    _, instructor_headers = await _make_instructor(client)
    course_id = (await client.post("/courses", json={"title": "LB Course", "slug": "lb-course-1"}, headers=instructor_headers)).json()["id"]
    await client.post(f"/courses/{course_id}/publish", headers=instructor_headers)

    _, student_headers = await auth_headers(client)
    await client.post(f"/courses/{course_id}/enroll", headers=student_headers)
    lesson_id = await _complete_single_lesson_course(client, instructor_headers, course_id)
    await client.post(f"/lessons/{lesson_id}/complete", headers=student_headers)

    resp = await client.get("/gamification/leaderboard", params={"limit": 10})
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) >= 1
    assert entries[0]["rank"] == 1
