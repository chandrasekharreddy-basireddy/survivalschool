"""Grid-format campus timetable parsing (the real Sai University spreadsheet
layout: day + time-range rows, one column per room, room name given in the
row directly below the class row) — sync, service-level unit tests, no
client/DB needed. See test_campus_timetable.py for the upload-endpoint
idempotency check using the same fixture CSV.

Regression coverage for two real bugs found against the actual production
spreadsheet: (1) a cell separated by a run of 2+ spaces rather than a dash
(e.g. "Subject    Faculty") must still split correctly, and (2) a "LUNCH
BREAK" marker can appear in any class-slot column, not just the time
column, and must not be misread as a class with the next row's subject
mistaken for its room.
"""
from __future__ import annotations

from app.services.campus_timetable_service import (
    _detect_format,
    _lab_course_name_and_code,
    _parse_csv_raw,
    _split_class_cell,
    parse_campus_rows,
)

GRID_CSV = (
    b"SemA Time Table from 03 August,,,,\n"
    b"MONDAY,09:15 AM -  10:10 AM,Data Structures - Sec 1 - Dr Rao,Linear Algebra    Iyer,\n"
    b",,AB2  -  101,AB2 - 102,\n"
    b"MONDAY,11:15 AM - 12:10 PM,LUNCH BREAK,,\n"
    b",,,,\n"
    b"TUESDAY,09:15 AM -  10:10 AM,Operating Systems - Sec 2 - Dr Nair,,\n"
    b",,AB3 - 201,,\n"
)


def test_split_class_cell_handles_dash_and_multi_space_separators():
    subject, faculty, section = _split_class_cell("Data Structures - Sec 1 - Dr Rao")
    assert (subject, faculty, section) == ("Data Structures", "Dr Rao", "1")

    # Multi-space separator, no section marker at all — must NOT have its
    # spacing collapsed before the split runs, or "Faculty" glues onto the
    # subject (the exact bug found against the real spreadsheet).
    subject, faculty, section = _split_class_cell("Linear Algebra & Instrumentation    Manobala")
    assert subject == "Linear Algebra & Instrumentation"
    assert faculty == "Manobala"
    assert section is None


def test_detect_format_recognizes_grid_layout():
    raw_rows = _parse_csv_raw(GRID_CSV)
    assert _detect_format(raw_rows) == "grid"


def test_parse_grid_rows_extracts_classes_and_skips_lunch():
    rows = parse_campus_rows("timetable.csv", GRID_CSV)
    assert all(r.error is None for r in rows)

    courses = {r.course_name for r in rows}
    assert courses == {"Data Structures", "Linear Algebra", "Operating Systems"}
    assert "LUNCH BREAK" not in courses

    ds = next(r for r in rows if r.course_name == "Data Structures")
    assert ds.teacher_name == "Dr Rao"
    assert ds.section == "1"
    assert ds.room == "AB2 - 101"

    la = next(r for r in rows if r.course_name == "Linear Algebra")
    assert la.teacher_name == "Iyer"
    assert la.room == "AB2 - 102"

    # 8 weeks ahead per weekly slot (see _GRID_WEEKS_AHEAD): 2 slots on
    # Monday + 1 on Tuesday, lunch contributing zero.
    assert len(rows) == 3 * 8


# --- Lab format: a third shape unique to the real workbook's per-lab
# schedule sheets — an explicit "Day | Time | Section" header, a single
# class-slot column with a combined "<prefix> Sec<N> <faculty>" cell, and
# no room anywhere in the sheet. The course itself comes from the sheet's
# own title row, not a column.

LAB_CSV = (
    b"Design and Analysis of Algorithms Lab (CS324) Schedule From 10-August-2026,,,\n"
    b"Day,Time,Section,\n"
    b"Monday,09:15 AM -  10:10 AM,DAA Sec2 david,\n"
    b",10:15 AM -  11:10 AM,LUNCH BREAK,\n"
    b",11.15 AM - 12.10 PM,DAA Sec 8 Rupam Sah,\n"
    # A genuinely different cell shape seen on two of the real workbook's
    # lab sheets: no numbered section at all, just a semester marker — see
    # _parse_lab_section_cell and _LAB_CELL_SEM_RE.
    b",12:15 PM -  12:55 PM,Programming in C LAB - Sem1 - Ujjwal,\n"
    b",01:15 PM - 01.55 PM,Nothing recognizable here,\n"
)


def test_lab_title_extracts_course_name_and_code():
    assert _lab_course_name_and_code(
        "Design and Analysis of Algorithms Lab (CS324) Schedule From 10-August-2026"
    ) == ("Design and Analysis of Algorithms Lab", "CS324")
    assert _lab_course_name_and_code("Emerging Tools Lab Schedule") == ("Emerging Tools Lab", None)


def test_detect_format_recognizes_lab_layout():
    raw_rows = _parse_csv_raw(LAB_CSV)
    assert _detect_format(raw_rows) == "lab"


def test_parse_lab_rows_extracts_section_and_faculty_skips_lunch_and_unrecognized_cells():
    rows = parse_campus_rows("lab.csv", LAB_CSV)
    assert all(r.error is None for r in rows)

    # 3 recognized slots (Sec2/david, Sec 8/Rupam Sah, Sem1/Ujjwal) x 8
    # weeks ahead; LUNCH BREAK and the genuinely unrecognizable cell
    # contribute nothing.
    assert len(rows) == 3 * 8

    sec2 = next(r for r in rows if r.section == "2")
    assert sec2.course_name == "Design and Analysis of Algorithms Lab"
    assert sec2.course_code == "CS324"
    assert sec2.teacher_name == "david"
    assert sec2.room is None

    sec8 = next(r for r in rows if r.section == "8")
    assert sec8.teacher_name == "Rupam Sah"

    sem1 = next(r for r in rows if r.section == "Sem1")
    assert sem1.teacher_name == "Ujjwal"
    assert sem1.course_name == "Design and Analysis of Algorithms Lab"

    assert "Programming in C LAB" not in {r.course_name for r in rows}


def test_multi_sheet_xlsx_parses_every_sheet_not_just_the_first():
    """The real workbook this whole feature is built against ships one
    grid-format main-schedule sheet plus several lab-schedule sheets in a
    single file — a student can only upload the one file, so every sheet
    has to be read, not just openpyxl's default first worksheet."""
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    grid_ws = wb.active
    grid_ws.title = "Main"
    for row in [
        ["SemA Time Table", "", "", ""],
        ["MONDAY", "09:15 AM -  10:10 AM", "Data Structures - Sec 1 - Dr Rao", ""],
        ["", "", "AB2 - 101", ""],
    ]:
        grid_ws.append(row)

    lab_ws = wb.create_sheet("Lab")
    for row in [
        ["Design and Analysis of Algorithms Lab (CS324) Schedule", "", "", ""],
        ["Day", "Time", "Section", ""],
        ["Monday", "09:15 AM -  10:10 AM", "DAA Sec2 david", ""],
    ]:
        lab_ws.append(row)

    buf = io.BytesIO()
    wb.save(buf)

    rows = parse_campus_rows("timetable.xlsx", buf.getvalue())
    courses = {r.course_name for r in rows}
    assert courses == {"Data Structures", "Design and Analysis of Algorithms Lab"}


# --- Personal upload of a grid/lab-format file: a student's actual copy of
# "the timetable" is often this same institution-wide spreadsheet, not a
# pre-filtered personal export — parse_personal_rows must recognize it (not
# blindly treat row 0 as a header and fail every row with "missing course
# name", the shape it used to be limited to) and reduce it to just the
# uploader's own section.

def test_personal_upload_of_a_grid_file_without_a_section_set_gives_a_clear_error():
    from app.core.exceptions import ValidationAppError
    from app.services.personal_timetable_service import parse_personal_rows

    try:
        parse_personal_rows("timetable.csv", GRID_CSV, section=None, school=None)
        raise AssertionError("expected a ValidationAppError")
    except ValidationAppError as e:
        assert "section" in str(e).lower()


def test_personal_upload_of_a_grid_file_filters_to_the_students_own_section():
    from app.services.personal_timetable_service import parse_personal_rows

    rows = parse_personal_rows("timetable.csv", GRID_CSV, section="1", school=None)
    assert all(r.error is None for r in rows)
    # Sec 1 explicitly, plus Linear Algebra which carries no section marker
    # at all and so defaults to "1" (see _parse_grid_rows) — neither
    # includes Sec 2's Operating Systems.
    assert {r.course_name for r in rows} == {"Data Structures", "Linear Algebra"}

    other_section = parse_personal_rows("timetable.csv", GRID_CSV, section="2", school=None)
    assert {r.course_name for r in other_section} == {"Operating Systems"}


def test_personal_upload_normalizes_a_prefixed_section_value():
    """Regression test: a profile section stored as "sec-1" (a person typed
    it, rather than picking from a real dropdown) must still match a
    spreadsheet cell's bare "1" — confirmed happening to a real user, whose
    upload silently produced "Imported 0 classes" with no explanation."""
    from app.services.personal_timetable_service import parse_personal_rows

    for variant in ("sec-1", "Section 1", "SEC 1", "sec.1", "01"):
        rows = parse_personal_rows("timetable.csv", GRID_CSV, section=variant, school=None)
        assert {r.course_name for r in rows} == {"Data Structures", "Linear Algebra"}, variant


def test_personal_upload_raises_a_clear_error_when_nothing_matches_the_section():
    """The old behavior here was a silent "0 imported, 0 errors" that
    looked like a success toast in the UI — the exact confusion a real
    user hit. A section that plainly doesn't exist in the file must fail
    loudly with an explanation instead."""
    from app.core.exceptions import ValidationAppError
    from app.services.personal_timetable_service import parse_personal_rows

    try:
        parse_personal_rows("timetable.csv", GRID_CSV, section="99", school=None)
        raise AssertionError("expected a ValidationAppError")
    except ValidationAppError as e:
        assert "section" in str(e).lower() and "99" in str(e)
