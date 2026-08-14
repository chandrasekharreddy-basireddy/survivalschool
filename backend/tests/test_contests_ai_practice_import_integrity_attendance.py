from __future__ import annotations

import asyncio
import io
from datetime import date, datetime, timedelta, timezone

import openpyxl
import pytest
from sqlalchemy import select

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
# Contests
# ---------------------------------------------------------------------------

async def test_contest_creation_is_admin_only(client):
    _, instructor = await _make_instructor(client)
    _, admin = await _make_admin(client)
    now = datetime.now(timezone.utc)

    forbidden = await client.post("/contests", json={
        "title": "Instructor Attempt", "starts_at": now.isoformat(), "ends_at": (now + timedelta(hours=1)).isoformat(),
        "question_ids": [],
    }, headers=instructor)
    assert forbidden.status_code == 403

    allowed = await client.post("/contests", json={
        "title": "Admin Contest", "starts_at": now.isoformat(), "ends_at": (now + timedelta(hours=1)).isoformat(),
        "question_ids": [],
    }, headers=admin)
    assert allowed.status_code == 201, allowed.text


async def test_contest_attempt_leaderboard_and_finalize_awards_top3_certificates(client):
    _, instructor = await _make_instructor(client)
    course_id = await _make_course(client, instructor, "Contest Source Course", "contest-source-course")
    q1 = await _make_question(client, instructor, course_id, "Contest Q1?", "Right1", "Wrong1")
    q2 = await _make_question(client, instructor, course_id, "Contest Q2?", "Right2", "Wrong2")

    _, admin = await _make_admin(client)
    now = datetime.now(timezone.utc)
    created = await client.post("/contests", json={
        "title": "Finalize Test Contest", "starts_at": (now - timedelta(minutes=1)).isoformat(),
        "ends_at": (now + timedelta(seconds=3)).isoformat(), "duration_seconds": 1800,
        "question_ids": [q1, q2], "top_n_awarded": 1,
    }, headers=admin)
    assert created.status_code == 201, created.text
    contest_id = created.json()["id"]
    assert created.json()["question_count"] == 2

    # Student A gets both right, student B gets one right — A should rank #1.
    _, student_a = await auth_headers(client)
    _, student_b = await auth_headers(client)

    for headers, get_both_right in ((student_a, True), (student_b, False)):
        start = await client.post(f"/contests/{contest_id}/attempts", headers=headers)
        assert start.status_code == 201, start.text
        qs = (await client.get(f"/contests/attempts/{start.json()['attempt_id']}/questions", headers=headers)).json()
        opts = {q["id"]: {o["text"]: o["id"] for o in q["options"]} for q in qs}
        answers = [{"question_id": q1, "selected_option_ids": [opts[q1]["Right1"]]}]
        if get_both_right:
            answers.append({"question_id": q2, "selected_option_ids": [opts[q2]["Right2"]]})
        else:
            answers.append({"question_id": q2, "selected_option_ids": [opts[q2]["Wrong2"]]})
        submit = await client.post(f"/contests/attempts/{start.json()['attempt_id']}/submit", json={"answers": answers}, headers=headers)
        assert submit.status_code == 200, submit.text

    # One attempt per student — a second attempt request is rejected.
    again = await client.post(f"/contests/{contest_id}/attempts", headers=student_a)
    assert again.status_code == 409

    leaderboard = (await client.get(f"/contests/{contest_id}/leaderboard")).json()
    assert leaderboard[0]["score_percent"] == 100

    # Wait out the contest window, then finalize.
    await asyncio.sleep(3.2)
    too_early_gone = await client.post(f"/contests/{contest_id}/finalize", headers=admin)
    assert too_early_gone.status_code == 200, too_early_gone.text
    assert too_early_gone.json()["status"] == "closed"

    my_certs_a = (await client.get("/contests/me/certificates", headers=student_a)).json()
    assert len(my_certs_a) == 1
    assert my_certs_a[0]["rank"] == 1

    # top_n_awarded was 1 — the second-place finisher gets no certificate.
    my_certs_b = (await client.get("/contests/me/certificates", headers=student_b)).json()
    assert len(my_certs_b) == 0

    verify = await client.get(f"/contests/certificates/verify/{my_certs_a[0]['certificate_number']}")
    assert verify.status_code == 200
    assert verify.json()["contest_title"] == "Finalize Test Contest"

    # Re-finalizing (e.g. a second worker tick) must not double-issue certificates.
    second = await client.post(f"/contests/{contest_id}/finalize", headers=admin)
    assert second.status_code == 200
    my_certs_a_again = (await client.get("/contests/me/certificates", headers=student_a)).json()
    assert len(my_certs_a_again) == 1


async def test_contest_scheduler_occurrence_key_is_idempotent(client):
    from app.database import AsyncSessionLocal
    from app.models.contest import Contest
    from app.services.contest_service import _create_if_missing

    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        first = await _create_if_missing(
            db, occurrence_key="test-occurrence-key-unique-1", title="Idempotency Test", description="",
            contest_type="weekly_morning", starts_at=now, ends_at=now + timedelta(hours=1), question_count=5,
        )
        assert first is not None
        second = await _create_if_missing(
            db, occurrence_key="test-occurrence-key-unique-1", title="Idempotency Test", description="",
            contest_type="weekly_morning", starts_at=now, ends_at=now + timedelta(hours=1), question_count=5,
        )
        await db.commit()
        assert second is None  # already exists — skipped, not duplicated

        count = len((await db.execute(
            select(Contest).where(Contest.occurrence_key == "test-occurrence-key-unique-1")
        )).scalars().all())
        assert count == 1


# ---------------------------------------------------------------------------
# AI mock practice
# ---------------------------------------------------------------------------

async def test_ai_mock_practice_generates_and_grades_server_side_with_zero_points(client):
    _, student = await auth_headers(client)
    before_points = (await client.get("/gamification/me", headers=student)).json()["total_points"]

    created = await client.post("/ai-practice/sessions", json={"subject": "Photosynthesis", "question_count": 3}, headers=student)
    assert created.status_code == 201, created.text
    session = created.json()
    assert session["provider"] == "mock"
    assert len(session["questions"]) == 3
    for q in session["questions"]:
        assert len(q["options"]) == 4

    # A resume fetch works while unsubmitted.
    resumed = await client.get(f"/ai-practice/sessions/{session['id']}/questions", headers=student)
    assert resumed.status_code == 200

    # Deliberately answer everything wrong (pick option index 1, never the
    # correct one at index 0 by MockAIProvider's construction) to prove
    # grading is server-side, not client-trusted.
    answers = [{"question_id": q["id"], "selected_option_ids": [q["options"][1]["id"]]} for q in session["questions"]]
    submitted = await client.post(f"/ai-practice/sessions/{session['id']}/submit", json={"answers": answers}, headers=student)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["score_percent"] == 0
    assert all(a["is_correct"] is False for a in submitted.json()["answers"])

    # Already submitted — resubmitting or fetching /questions now 409s; the result endpoint works.
    conflict = await client.post(f"/ai-practice/sessions/{session['id']}/submit", json={"answers": answers}, headers=student)
    assert conflict.status_code == 409
    result = await client.get(f"/ai-practice/sessions/{session['id']}", headers=student)
    assert result.status_code == 200

    after_points = (await client.get("/gamification/me", headers=student)).json()["total_points"]
    assert after_points == before_points  # AI mock practice never awards gamification points

    history = (await client.get("/ai-practice/me/sessions", headers=student)).json()
    assert any(h["id"] == session["id"] for h in history)


async def test_ai_mock_practice_never_appears_in_real_question_bank(client):
    """The whole point of the separate table set: an AI-generated question
    must never be selectable as a real Question row (e.g. by the contest
    question-selection service, which only ever queries the `questions`
    table joined to published courses)."""
    _, student = await auth_headers(client)
    created = (await client.post("/ai-practice/sessions", json={"subject": "History", "question_count": 3}, headers=student)).json()
    ai_question_ids = {q["id"] for q in created["questions"]}

    from app.database import AsyncSessionLocal
    from app.models.assessment import Question

    async with AsyncSessionLocal() as db:
        real_ids = {str(i) for i in (await db.execute(select(Question.id))).scalars().all()}
    assert ai_question_ids.isdisjoint(real_ids)


# ---------------------------------------------------------------------------
# Bulk question import
# ---------------------------------------------------------------------------

_CSV_VALID = (
    "prompt,question_type,points,option_1,option_1_correct,option_2,option_2_correct\n"
    "What is 2+2?,single,1,4,true,5,false\n"
    "Sky color?,single,1,Blue,true,Green,false\n"
)

_CSV_ONE_BAD_ROW = (
    "prompt,question_type,points,option_1,option_1_correct,option_2,option_2_correct\n"
    "Good row,single,1,Right,true,Wrong,false\n"
    "Bad row - no correct option,single,1,A,false,B,false\n"
)


async def test_bulk_import_csv_preview_then_commit(client):
    _, instructor = await _make_instructor(client)
    course_id = await _make_course(client, instructor, "Bulk Import Course", "bulk-import-course")

    files = {"file": ("questions.csv", _CSV_VALID.encode(), "text/csv")}
    preview = await client.post(f"/questions/bulk-import?course_id={course_id}", files=files, headers=instructor)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["total_rows"] == 2 and body["valid_rows"] == 2 and body["error_rows"] == 0
    assert body["committed"] is False and body["inserted_count"] == 0

    files = {"file": ("questions.csv", _CSV_VALID.encode(), "text/csv")}
    commit = await client.post(f"/questions/bulk-import?course_id={course_id}&dry_run=false", files=files, headers=instructor)
    assert commit.status_code == 200, commit.text
    assert commit.json()["committed"] is True
    assert commit.json()["inserted_count"] == 2


async def test_bulk_import_all_or_nothing_on_row_error(client):
    _, instructor = await _make_instructor(client)
    course_id = await _make_course(client, instructor, "Bulk Import Bad Course", "bulk-import-bad-course")

    files = {"file": ("questions.csv", _CSV_ONE_BAD_ROW.encode(), "text/csv")}
    commit = await client.post(f"/questions/bulk-import?course_id={course_id}&dry_run=false", files=files, headers=instructor)
    assert commit.status_code == 200, commit.text
    body = commit.json()
    assert body["error_rows"] == 1
    assert body["committed"] is False
    assert body["inserted_count"] == 0
    bad_row = next(r for r in body["rows"] if r["error"])
    assert "exactly one correct option" in bad_row["error"]


async def test_bulk_import_rejects_non_owner_instructor(client):
    _, owner = await _make_instructor(client)
    _, other = await _make_instructor(client)
    course_id = await _make_course(client, owner, "Bulk Import Owned Course", "bulk-import-owned-course")

    files = {"file": ("questions.csv", _CSV_VALID.encode(), "text/csv")}
    resp = await client.post(f"/questions/bulk-import?course_id={course_id}", files=files, headers=other)
    assert resp.status_code == 403


async def test_bulk_import_xlsx(client):
    _, instructor = await _make_instructor(client)
    course_id = await _make_course(client, instructor, "Bulk Import XLSX Course", "bulk-import-xlsx-course")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["prompt", "question_type", "points", "option_1", "option_1_correct", "option_2", "option_2_correct"])
    ws.append(["XLSX question?", "single", 1, "Right", True, "Wrong", False])
    buf = io.BytesIO()
    wb.save(buf)

    files = {"file": ("questions.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    commit = await client.post(f"/questions/bulk-import?course_id={course_id}&dry_run=false", files=files, headers=instructor)
    assert commit.status_code == 200, commit.text
    assert commit.json()["inserted_count"] == 1


# ---------------------------------------------------------------------------
# Exam integrity
# ---------------------------------------------------------------------------

async def test_exam_integrity_events_are_logged_and_reviewable_by_instructor(client):
    _, instructor = await _make_instructor(client)
    course_id = await _make_course(client, instructor, "Integrity Course", "integrity-course")
    question_id = await _make_question(client, instructor, course_id, "Integrity Q?", "Right", "Wrong")
    exam_id = (await client.post("/exams", json={
        "course_id": course_id, "title": "Integrity Exam", "time_limit_seconds": 3600,
        "question_ids": [question_id], "fullscreen_required": True,
    }, headers=instructor)).json()["id"]
    await client.post(f"/exams/{exam_id}/publish", headers=instructor)

    _, student = await auth_headers(client)
    start = await client.post(f"/exams/{exam_id}/attempts", headers=student)
    attempt_id = start.json()["attempt_id"]

    logged = await client.put(f"/exams/attempts/{attempt_id}/events", json={"event_type": "tab_blur"}, headers=student)
    assert logged.status_code == 200 and logged.json()["logged"] is True
    await client.put(f"/exams/attempts/{attempt_id}/events", json={"event_type": "fullscreen_exit"}, headers=student)

    flagged = await client.get(f"/exams/{exam_id}/attempts/flagged", headers=instructor)
    assert flagged.status_code == 200
    assert len(flagged.json()) == 1
    assert len(flagged.json()[0]["flagged_events"]) == 2
    assert {e["type"] for e in flagged.json()[0]["flagged_events"]} == {"tab_blur", "fullscreen_exit"}

    # A different instructor can't see this exam's integrity data.
    _, other_instructor = await _make_instructor(client)
    forbidden = await client.get(f"/exams/{exam_id}/attempts/flagged", headers=other_instructor)
    assert forbidden.status_code == 403

    # Events stop being accepted once the attempt is submitted.
    qs = (await client.get(f"/exams/attempts/{attempt_id}/questions", headers=student)).json()
    correct_id = next(o["id"] for o in qs[0]["options"] if o["text"] == "Right")
    await client.post(f"/exams/attempts/{attempt_id}/submit", json={
        "answers": [{"question_id": question_id, "selected_option_ids": [correct_id]}],
    }, headers=student)
    post_submit = await client.put(f"/exams/attempts/{attempt_id}/events", json={"event_type": "copy"}, headers=student)
    assert post_submit.json()["logged"] is False


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

async def _make_timetable_entry_for_today(client, instructor, course_id):
    today_weekday = date.today().weekday()
    resp = await client.post("/timetable", json={
        "course_id": course_id, "term": "2026-Fall", "term_start_date": "2026-01-01", "term_end_date": "2026-12-31",
        "day_of_week": today_weekday, "start_time": "09:00:00", "end_time": "10:00:00", "room": "Attendance Room",
    }, headers=instructor)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_attendance_open_requires_actual_scheduled_day(client):
    _, instructor = await _make_instructor(client)
    course_id = await _make_course(client, instructor, "Attendance Day Course", "attendance-day-course")
    wrong_weekday = (date.today().weekday() + 1) % 7
    entry_id = (await client.post("/timetable", json={
        "course_id": course_id, "term": "2026-Fall", "term_start_date": "2026-01-01", "term_end_date": "2026-12-31",
        "day_of_week": wrong_weekday, "start_time": "09:00:00", "end_time": "10:00:00", "room": "R1",
    }, headers=instructor)).json()["id"]

    resp = await client.post("/attendance/sessions/open", json={"timetable_entry_id": entry_id}, headers=instructor)
    assert resp.status_code == 422, resp.text


async def test_attendance_check_in_flow_and_manual_marking(client):
    _, instructor = await _make_instructor(client)
    course_id = await _make_course(client, instructor, "Attendance Flow Course", "attendance-flow-course")
    entry_id = await _make_timetable_entry_for_today(client, instructor, course_id)

    opened = await client.post("/attendance/sessions/open", json={"timetable_entry_id": entry_id}, headers=instructor)
    assert opened.status_code == 201, opened.text
    session_id = opened.json()["id"]
    code = opened.json()["check_in_code"]

    _, enrolled_student = await auth_headers(client)
    await client.post(f"/courses/{course_id}/enroll", headers=enrolled_student)
    _, outsider = await auth_headers(client)

    wrong_code = await client.post("/attendance/check-in", json={"code": "ZZZZZZ"}, headers=enrolled_student)
    assert wrong_code.status_code == 409

    not_enrolled = await client.post("/attendance/check-in", json={"code": code}, headers=outsider)
    assert not_enrolled.status_code == 403

    checked_in = await client.post("/attendance/check-in", json={"code": code}, headers=enrolled_student)
    assert checked_in.status_code == 200, checked_in.text
    assert checked_in.json()["status"] == "present"

    # Idempotent — checking in twice doesn't create two records.
    again = await client.post("/attendance/check-in", json={"code": code}, headers=enrolled_student)
    assert again.status_code == 200
    assert again.json()["id"] == checked_in.json()["id"]

    _, second_enrolled = await auth_headers(client)
    await client.post(f"/courses/{course_id}/enroll", headers=second_enrolled)
    marked = await client.post(f"/attendance/sessions/{session_id}/mark", json={
        "student_id": (await client.get("/auth/me", headers=second_enrolled)).json()["id"], "status": "excused",
    }, headers=instructor)
    assert marked.status_code == 200
    assert marked.json()["status"] == "excused"

    roster = await client.get(f"/attendance/sessions/{session_id}", headers=instructor)
    assert roster.status_code == 200
    statuses = {r["status"] for r in roster.json()}
    assert "present" in statuses and "excused" in statuses

    summary = (await client.get("/attendance/me", headers=enrolled_student)).json()
    course_summary = next(s for s in summary if s["course_id"] == course_id)
    assert course_summary["total_sessions"] == 1
    assert course_summary["present_count"] == 1
    assert course_summary["attendance_percent"] == 100
