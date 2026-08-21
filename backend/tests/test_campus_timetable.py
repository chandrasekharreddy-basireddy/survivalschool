"""Campus timetable: upload -> real distinct sections for the frontend
dropdown (GET /timetable/campus/sections) -> a student's own filtered
schedule (GET /timetable/campus/me), keyed off profile.section rather than
a blind free-text guess. No prior coverage existed for this feature at all."""
from __future__ import annotations

import pytest

from tests.conftest import auth_headers, grant_role, login
from tests.test_campus_timetable_grid_parsing import GRID_CSV

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _make_admin(client):
    email, headers = await auth_headers(client)
    await grant_role(email, "ADMIN")
    tokens = await login(client, email)
    return email, {"Authorization": f"Bearer {tokens['access_token']}"}


_CSV = (
    b"School,Year,Section,LabGroup,Course,CourseId,Date,StartTime,EndTime,Room,Teacher,Elective\n"
    b"SCDS,3,A,,Data Structures,CS301,2027-03-01,09:00,10:00,101,Dr. Rao,\n"
    b"SCDS,3,A,L1,Data Structures Lab,CS301L,2027-03-01,11:00,13:00,Lab-1,Dr. Rao,\n"
    b"SCDS,3,B,,Data Structures,CS301,2027-03-01,10:00,11:00,102,Dr. Rao,\n"
    b"SOAI,2,A,,Linear Algebra,MA201,2027-03-01,09:00,10:00,201,Dr. Iyer,\n"
)


async def test_upload_then_sections_reflects_real_distinct_combinations(client):
    _, admin = await _make_admin(client)
    resp = await client.post(
        "/timetable/campus/upload",
        files={"file": ("timetable.csv", _CSV, "text/csv")},
        headers=admin,
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["created"] == 4
    assert result["error_rows"] == []

    sections = (await client.get("/timetable/campus/sections", headers=admin)).json()
    scds_a = next(s for s in sections if s["school"] == "SCDS" and s["section"] == "A")
    assert scds_a["year_of_study"] == "3"
    assert scds_a["lab_groups"] == ["L1"]

    scds_b = next(s for s in sections if s["school"] == "SCDS" and s["section"] == "B")
    assert scds_b["lab_groups"] == []

    soai_a = next(s for s in sections if s["school"] == "SOAI" and s["section"] == "A")
    assert soai_a["year_of_study"] == "2"


async def test_two_lab_groups_at_the_same_slot_dont_collide_on_upload(client):
    """Regression test: row_key used to omit lab_group from its identity,
    so two parallel lab-group sections of the same course meeting at the
    identical section/date/start_time (different room/teacher per group —
    a completely normal real-world shape) hashed to the SAME key. The
    second row's upsert silently overwrote the first instead of creating
    a second row, so one lab group's room/teacher just vanished. Both
    must now survive as two distinct rows."""
    _, admin = await _make_admin(client)
    csv_bytes = (
        b"School,Year,Section,LabGroup,Course,CourseId,Date,StartTime,EndTime,Room,Teacher,Elective\n"
        b"SCDS,3,A,1,Data Structures Lab,CS301L,2027-03-01,11:00,13:00,Lab-1,Dr. Rao,\n"
        b"SCDS,3,A,2,Data Structures Lab,CS301L,2027-03-01,11:00,13:00,Lab-2,Prof. Iyer,\n"
    )
    resp = await client.post(
        "/timetable/campus/upload",
        files={"file": ("timetable.csv", csv_bytes, "text/csv")},
        headers=admin,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] == 2

    entries = (await client.get(
        "/timetable/campus?section=A&date_from=2027-03-01&date_to=2027-03-01", headers=admin
    )).json()
    lab_entries = [e for e in entries if e["course_code"] == "CS301L"]
    rooms = {e["room"] for e in lab_entries}
    assert rooms == {"Lab-1", "Lab-2"}


async def test_sections_endpoint_requires_auth_but_not_admin(client):
    anon = await client.get("/timetable/campus/sections")
    assert anon.status_code == 401

    _, student = await auth_headers(client)
    resp = await client.get("/timetable/campus/sections", headers=student)
    assert resp.status_code == 200, resp.text


async def test_upload_gated_to_admin(client):
    _, student = await auth_headers(client)
    resp = await client.post(
        "/timetable/campus/upload",
        files={"file": ("t.csv", _CSV, "text/csv")},
        headers=student,
    )
    assert resp.status_code == 403, resp.text


async def test_my_entries_requires_section_then_filters_by_it(client):
    _, admin = await _make_admin(client)
    upload = await client.post(
        "/timetable/campus/upload",
        files={"file": ("timetable.csv", _CSV, "text/csv")},
        headers=admin,
    )
    assert upload.status_code == 200, upload.text

    _, student = await auth_headers(client)
    before = await client.get("/timetable/campus/me", headers=student)
    assert before.status_code == 422, before.text

    # section alone, no school set — matches "A" in *any* school, same as
    # before profiles.school existed (backward-compatible fallback).
    patched = await client.patch("/users/me/profile", json={"section": "A"}, headers=student)
    assert patched.status_code == 200, patched.text
    mine = await client.get("/timetable/campus/me?date_from=2027-01-01", headers=student)
    courses = {e["course_name"] for e in mine.json()}
    assert "Data Structures" in courses and "Linear Algebra" in courses

    # Setting school too disambiguates — SOAI's "Linear Algebra" (also
    # section A) must no longer show up for an SCDS student.
    scoped = await client.patch("/users/me/profile", json={"school": "SCDS"}, headers=student)
    assert scoped.status_code == 200, scoped.text
    mine_scoped = await client.get("/timetable/campus/me?date_from=2027-01-01", headers=student)
    scoped_courses = {e["course_name"] for e in mine_scoped.json()}
    assert "Data Structures" in scoped_courses
    assert "Linear Algebra" not in scoped_courses


_PERSONAL_CSV = (
    b"Course,CourseId,Date,StartTime,EndTime,Room,Teacher,Elective\n"
    b"Operating Systems,CS401,2027-03-02,09:00,10:00,301,Dr. Nair,\n"
    b"Operating Systems Lab,CS401L,2027-03-02,14:00,16:00,Lab-3,Dr. Nair,1\n"
)


async def test_personal_upload_is_scoped_to_the_uploader_and_never_touches_the_campus_feed(client):
    _, student_a = await auth_headers(client)
    resp = await client.post(
        "/timetable/me/upload",
        files={"file": ("mine.csv", _PERSONAL_CSV, "text/csv")},
        headers=student_a,
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["imported"] == 2
    assert result["error_rows"] == []

    mine = await client.get("/timetable/me/personal?date_from=2027-01-01", headers=student_a)
    assert mine.status_code == 200, mine.text
    courses = {e["course_name"] for e in mine.json()}
    assert courses == {"Operating Systems", "Operating Systems Lab"}
    lab = next(e for e in mine.json() if e["course_name"] == "Operating Systems Lab")
    assert lab["is_elective"] is True

    # A second student's own view (and the shared campus feed) must be
    # completely unaffected by student_a's upload.
    _, student_b = await auth_headers(client)
    theirs = await client.get("/timetable/me/personal?date_from=2027-01-01", headers=student_b)
    assert theirs.json() == []

    campus = await client.get("/timetable/campus?date_from=2027-01-01", headers=student_b)
    assert campus.status_code == 200, campus.text
    assert "Operating Systems" not in {e["course_name"] for e in campus.json()}


async def test_personal_upload_replaces_previous_upload_wholesale(client):
    _, student = await auth_headers(client)
    first = await client.post(
        "/timetable/me/upload",
        files={"file": ("first.csv", _PERSONAL_CSV, "text/csv")},
        headers=student,
    )
    assert first.status_code == 200, first.text

    second_csv = b"Course,Date,StartTime,EndTime\nOnly This Class,2027-03-05,09:00,10:00\n"
    second = await client.post(
        "/timetable/me/upload",
        files={"file": ("second.csv", second_csv, "text/csv")},
        headers=student,
    )
    assert second.status_code == 200, second.text
    assert second.json()["imported"] == 1

    mine = await client.get("/timetable/me/personal?date_from=2027-01-01", headers=student)
    assert [e["course_name"] for e in mine.json()] == ["Only This Class"]


async def test_personal_upload_rejects_bad_rows_without_importing_anything(client):
    _, student = await auth_headers(client)
    bad_csv = b"Course,Date,StartTime,EndTime\nNo Times,2027-03-05,,\n"
    resp = await client.post(
        "/timetable/me/upload",
        files={"file": ("bad.csv", bad_csv, "text/csv")},
        headers=student,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported"] == 0
    assert len(body["error_rows"]) == 1

    mine = await client.get("/timetable/me/personal", headers=student)
    assert mine.json() == []


async def test_clear_personal_timetable(client):
    _, student = await auth_headers(client)
    await client.post("/timetable/me/upload", files={"file": ("mine.csv", _PERSONAL_CSV, "text/csv")}, headers=student)

    cleared = await client.delete("/timetable/me/personal", headers=student)
    assert cleared.status_code == 200, cleared.text

    mine = await client.get("/timetable/me/personal?date_from=2027-01-01", headers=student)
    assert mine.json() == []


async def test_personal_upload_does_not_require_admin(client):
    """The whole point of the feature: any verified student can use it, not
    just admins."""
    _, student = await auth_headers(client)
    resp = await client.post(
        "/timetable/me/upload",
        files={"file": ("mine.csv", _PERSONAL_CSV, "text/csv")},
        headers=student,
    )
    assert resp.status_code == 200, resp.text


# --- Grid format (real Sai University spreadsheet layout) upload-level
# idempotency check. See test_campus_timetable_grid_parsing.py for the
# format-detection and parsing unit tests (sync, no client/DB needed).


async def test_grid_upload_is_idempotent_on_reupload(client):
    _, admin = await _make_admin(client)
    first = await client.post(
        "/timetable/campus/upload",
        files={"file": ("timetable.csv", GRID_CSV, "text/csv")},
        headers=admin,
    )
    assert first.status_code == 200, first.text
    first_result = first.json()
    assert first_result["created"] == 24
    assert first_result["error_rows"] == []

    second = await client.post(
        "/timetable/campus/upload",
        files={"file": ("timetable.csv", GRID_CSV, "text/csv")},
        headers=admin,
    )
    assert second.status_code == 200, second.text
    second_result = second.json()
    assert second_result["created"] == 0
    assert second_result["updated"] == 0


# --- Timetable chat: scoped strictly to the student's own real, already-
# parsed schedule data (their personal upload if they have one, else their
# section's campus feed) — never a free-floating AI chat.


async def test_chat_with_no_schedule_data_says_so_without_calling_ai(client):
    _, student = await auth_headers(client)
    resp = await client.post("/timetable/me/chat", json={"question": "What's my next class?"}, headers=student)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider"] == "none"
    assert "don't have" in body["answer"].lower()


async def test_chat_rejects_empty_question(client):
    _, student = await auth_headers(client)
    resp = await client.post("/timetable/me/chat", json={"question": "   "}, headers=student)
    assert resp.status_code == 422, resp.text


async def test_chat_answers_from_the_students_personal_upload(client):
    # The chat endpoint's schedule window is relative to today, unlike
    # _PERSONAL_CSV's fixed far-future dates — build one with a near-term
    # date so it actually falls inside that window.
    import datetime as _dt

    near_date = (_dt.date.today() + _dt.timedelta(days=2)).isoformat()
    csv_bytes = (
        b"Course,CourseId,Date,StartTime,EndTime,Room,Teacher,Elective\n"
        + f"Operating Systems,CS401,{near_date},09:00,10:00,301,Dr. Nair,\n".encode()
    )

    _, student = await auth_headers(client)
    upload = await client.post(
        "/timetable/me/upload",
        files={"file": ("mine.csv", csv_bytes, "text/csv")},
        headers=student,
    )
    assert upload.status_code == 200, upload.text

    resp = await client.post("/timetable/me/chat", json={"question": "When is Operating Systems?"}, headers=student)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider"] == "mock"
    assert body["answer"]


# --- Teacher directory, electives, and free rooms — all derived from
# "this week's pattern" (a 7-day window from today, or "right now" for
# free rooms), not the fixed far-future dates most fixtures above use.


async def _dynamic_csv(rows_after_header: list[str]) -> bytes:
    header = "School,Year,Section,LabGroup,Course,CourseId,Date,StartTime,EndTime,Room,Teacher,Elective\n"
    return (header + "".join(rows_after_header)).encode()


async def test_teachers_lists_weekly_class_and_day_counts_not_raw_row_count(client):
    import datetime as _dt

    _, admin = await _make_admin(client)
    d1 = (_dt.date.today() + _dt.timedelta(days=1)).isoformat()
    d2 = (_dt.date.today() + _dt.timedelta(days=2)).isoformat()
    csv_bytes = await _dynamic_csv([
        f"SCDS,3,A,,Data Structures,CS301,{d1},09:00,10:00,101,Dr. Rao,\n",
        f"SCDS,3,A,,Operating Systems,CS401,{d2},09:00,10:00,102,Dr. Rao,\n",
        # Same teacher, same day as the first row — must still count as 2
        # distinct classes but only 1 distinct day for that pairing.
        f"SCDS,3,B,,Linear Algebra,MA201,{d1},11:00,12:00,103,Dr. Rao,\n",
    ])
    upload = await client.post("/timetable/campus/upload", files={"file": ("t.csv", csv_bytes, "text/csv")}, headers=admin)
    assert upload.status_code == 200, upload.text

    resp = await client.get("/timetable/campus/teachers", headers=admin)
    assert resp.status_code == 200, resp.text
    rao = next(t for t in resp.json() if t["teacher_name"] == "Dr. Rao")
    assert rao["class_count"] == 3
    assert rao["day_count"] == 2


async def test_electives_groups_distinct_sections_under_each_course(client):
    import datetime as _dt

    _, admin = await _make_admin(client)
    d1 = (_dt.date.today() + _dt.timedelta(days=1)).isoformat()
    csv_bytes = await _dynamic_csv([
        f"SCDS,2,1,,Emerging Tools,ET101,{d1},09:00,10:00,201,Arjun Singh,1\n",
        f"SCDS,2,2,,Emerging Tools,ET101,{d1},10:00,11:00,202,Sonar,1\n",
        f"SCDS,2,1,,Data Structures,CS301,{d1},11:00,12:00,101,Dr. Rao,\n",  # not an elective
    ])
    upload = await client.post("/timetable/campus/upload", files={"file": ("t.csv", csv_bytes, "text/csv")}, headers=admin)
    assert upload.status_code == 200, upload.text

    resp = await client.get("/timetable/campus/electives", headers=admin)
    assert resp.status_code == 200, resp.text
    electives = {e["course_name"] for e in resp.json()}
    assert "Emerging Tools" in electives
    assert "Data Structures" not in electives

    et = next(e for e in resp.json() if e["course_name"] == "Emerging Tools")
    sections = {(s["section"], s["teacher_name"]) for s in et["sections"]}
    assert sections == {("1", "Arjun Singh"), ("2", "Sonar")}


async def test_free_rooms_excludes_rooms_occupied_today_includes_rooms_only_used_on_other_days(client):
    import datetime as _dt

    _, admin = await _make_admin(client)
    today = _dt.date.today().isoformat()
    other_day = (_dt.date.today() + _dt.timedelta(days=3)).isoformat()
    csv_bytes = await _dynamic_csv([
        # Covers the whole day today — guaranteed to include "right now"
        # regardless of what time this test actually runs.
        f"SCDS,3,A,,All Day Class,CS999,{today},00:00,23:59,OCCUPIED-ROOM,Dr. Rao,\n",
        # Only ever scheduled on a different date — never occupied today.
        f"SCDS,3,A,,Some Other Class,CS998,{other_day},09:00,10:00,FREE-ROOM,Dr. Iyer,\n",
    ])
    upload = await client.post("/timetable/campus/upload", files={"file": ("t.csv", csv_bytes, "text/csv")}, headers=admin)
    assert upload.status_code == 200, upload.text

    resp = await client.get("/timetable/campus/free-rooms", headers=admin)
    assert resp.status_code == 200, resp.text
    rooms = resp.json()
    assert "OCCUPIED-ROOM" not in rooms
    assert "FREE-ROOM" in rooms


async def test_list_entries_filters_by_teacher(client):
    import datetime as _dt

    _, admin = await _make_admin(client)
    d1 = (_dt.date.today() + _dt.timedelta(days=1)).isoformat()
    csv_bytes = await _dynamic_csv([
        f"SCDS,3,A,,Data Structures,CS301,{d1},09:00,10:00,101,Dr. Rao,\n",
        f"SCDS,3,A,,Linear Algebra,MA201,{d1},10:00,11:00,102,Dr. Iyer,\n",
    ])
    upload = await client.post("/timetable/campus/upload", files={"file": ("t.csv", csv_bytes, "text/csv")}, headers=admin)
    assert upload.status_code == 200, upload.text

    # date_from/date_to scope to just this test's own upload — list_campus_entries
    # has no default date window (unlike /me), so an unscoped query would also
    # pick up any other test's "Dr. Rao" rows sharing this session-wide DB.
    resp = await client.get(f"/timetable/campus?teacher=Dr. Rao&date_from={d1}&date_to={d1}", headers=admin)
    assert resp.status_code == 200, resp.text
    assert {e["course_name"] for e in resp.json()} == {"Data Structures"}
