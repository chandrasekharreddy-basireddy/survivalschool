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
    # A genuinely different, semester-based cell shape ("Sem1" rather than
    # a numbered section) seen on two of the real workbook's lab sheets —
    # deliberately NOT guessed at (see _parse_lab_rows' docstring): section
    # cells that don't match "<prefix> Sec<N> <faculty>" are skipped
    # rather than treating "Sem1" as if it were a section number.
    b",12:15 PM -  12:55 PM,Programming in C LAB - Sem1 - Ujjwal,\n"
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

    # 2 recognized slots (Sec2/david, Sec 8/Rupam Sah) x 8 weeks ahead;
    # LUNCH BREAK and the unrecognized "Sem1" cell contribute nothing.
    assert len(rows) == 2 * 8

    sec2 = next(r for r in rows if r.section == "2")
    assert sec2.course_name == "Design and Analysis of Algorithms Lab"
    assert sec2.course_code == "CS324"
    assert sec2.teacher_name == "david"
    assert sec2.room is None

    sec8 = next(r for r in rows if r.section == "8")
    assert sec8.teacher_name == "Rupam Sah"

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
