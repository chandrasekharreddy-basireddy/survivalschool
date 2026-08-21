"""AI-assisted timetable extraction: the fallback path for a spreadsheet
sheet whose layout none of the three deterministic parsers (list/grid/lab
in campus_timetable_service.py) recognize. Covers three separate things:
(1) SarvamAIProvider.extract_timetable_rows's grounding check — the whole
point of it existing is that it must never surface a value the AI didn't
actually find in the given text, even if the AI ignores that instruction;
(2) MockAIProvider's honest "no AI available" empty result; (3) the
fallback wiring itself — a well-formed list-format sheet never invokes
the AI at all, a genuinely unrecognizable one does, and its results only
replace the original per-row errors when the AI found something real."""
from __future__ import annotations

import pytest

from app.services.ai_provider import (
    AIGenerationError,
    AIResponse,
    ExtractedTimetableRow,
    MockAIProvider,
    SarvamAIProvider,
)
from app.services.campus_timetable_service import (
    _AI_FALLBACK_ERROR_RATE,
    _ai_extract_sheet,
    _parse_csv_raw,
    _parse_one_sheet_async,
    parse_campus_rows_async,
)


async def test_mock_provider_returns_nothing_rather_than_fabricated_data():
    rows = await MockAIProvider().extract_timetable_rows("row 1: Monday | 09:00 AM - 10:00 AM | Some Class")
    assert rows == []


async def test_sarvam_provider_drops_ungrounded_fields_and_ungrounded_entries(monkeypatch):
    provider = SarvamAIProvider()
    raw_text = "row 1: Monday | 09:15 AM - 10:10 AM | Web Technology - Sec 4 - Rupam Sah"

    async def fake_chat(messages, *, system_prompt=None, image_data_url=None):
        import json
        payload = json.dumps([
            # Real entry, fully grounded — every field appears in raw_text.
            {"day": "Monday", "start_time": "09:15 AM", "end_time": "10:10 AM",
             "course_name": "Web Technology", "section": "4", "teacher_name": "Rupam Sah",
             "room": None, "school": None, "year": None},
            # Same entry, but with a hallucinated room the source text never
            # mentions — the room must be dropped, not the whole entry,
            # since day/time/course_name are still genuinely grounded.
            {"day": "Monday", "start_time": "09:15 AM", "end_time": "10:10 AM",
             "course_name": "Web Technology", "section": "4", "teacher_name": "Rupam Sah",
             "room": "AB9 - 999 (made up)", "school": None, "year": None},
            # Entirely fabricated entry with no basis in raw_text at all —
            # the whole item must be dropped.
            {"day": "Tuesday", "start_time": "11:00 AM", "end_time": "12:00 PM",
             "course_name": "Quantum Basket Weaving", "section": None, "teacher_name": None,
             "room": None, "school": None, "year": None},
        ])
        return AIResponse(content=payload, provider="sarvam", tokens_used=10, latency_ms=5)

    monkeypatch.setattr(provider, "chat", fake_chat)
    rows = await provider.extract_timetable_rows(raw_text)

    assert len(rows) == 2
    assert all(r.course_name == "Web Technology" for r in rows)
    assert rows[0].room is None
    assert rows[1].room is None  # the hallucinated room was dropped, not trusted
    assert "Quantum Basket Weaving" not in {r.course_name for r in rows}


async def test_sarvam_provider_raises_on_invalid_json(monkeypatch):
    provider = SarvamAIProvider()

    async def fake_chat(messages, *, system_prompt=None, image_data_url=None):
        return AIResponse(content="not json at all", provider="sarvam", tokens_used=5, latency_ms=5)

    monkeypatch.setattr(provider, "chat", fake_chat)
    with pytest.raises(AIGenerationError):
        await provider.extract_timetable_rows("row 1: whatever")


class _FakeProvider:
    """A minimal stand-in AIProvider — only extract_timetable_rows is
    exercised by the code under test, so nothing else needs implementing."""

    def __init__(self, rows: list[ExtractedTimetableRow]):
        self._rows = rows

    async def extract_timetable_rows(self, raw_text: str) -> list[ExtractedTimetableRow]:
        return self._rows


async def test_ai_extract_sheet_converts_to_parsed_campus_rows():
    fake = _FakeProvider([
        ExtractedTimetableRow(
            day="Wednesday", start_time="02:00 PM", end_time="02:55 PM",
            course_name="Ad-Hoc Seminar", section="3", teacher_name="Dr. Rao",
            room="Hall B", school="SCDS", year="2",
        ),
        # Missing a required field (end_time) — must be skipped, not crash.
        ExtractedTimetableRow(day="Wednesday", start_time="03:00 PM", end_time=None, course_name="Broken Entry"),
    ])
    rows = await _ai_extract_sheet([["irrelevant — chunking doesn't matter for this test"]], fake)

    assert all(r.course_name == "Ad-Hoc Seminar" for r in rows)
    assert {r.class_date.weekday() for r in rows} == {2}  # Wednesday
    # 8 weeks ahead, same as the deterministic grid/lab parsers.
    assert len(rows) == 8
    assert rows[0].section == "3"
    assert rows[0].teacher_name == "Dr. Rao"
    assert rows[0].room == "Hall B"
    assert rows[0].school == "SCDS"
    assert rows[0].year_of_study == "2"


_WELL_FORMED_LIST_CSV = (
    b"Course,Section,Date,StartTime,EndTime,Room,Teacher\n"
    b"Data Structures,A,2027-03-01,09:00,10:00,101,Dr. Rao\n"
    b"Linear Algebra,A,2027-03-01,10:00,11:00,102,Dr. Iyer\n"
)

# No day/time/course columns at all, unlike any of the three recognized
# shapes — every row fails as list-format, which is exactly the "clumsy,
# unrecognized layout" _AI_FALLBACK_ERROR_RATE exists to catch.
_UNRECOGNIZABLE_CSV = (
    b"Notes\n"
    b"whatever this is, it isn't a timetable in any format the deterministic parsers know\n"
    b"neither is this\n"
)


async def test_well_formed_list_sheet_never_invokes_ai_fallback():
    calls = []

    class _CountingProvider(_FakeProvider):
        async def extract_timetable_rows(self, raw_text: str) -> list[ExtractedTimetableRow]:
            calls.append(raw_text)
            return []

    raw_rows = _parse_csv_raw(_WELL_FORMED_LIST_CSV)
    rows = await _parse_one_sheet_async(raw_rows, use_ai_fallback=True)

    assert calls == []  # AI never called — error rate was well under the threshold
    assert all(r.error is None for r in rows)
    assert len(rows) == 2


async def test_unrecognizable_sheet_falls_back_to_ai_and_uses_its_result(monkeypatch):
    import app.services.campus_timetable_service as campus_timetable_service

    fake = _FakeProvider([
        ExtractedTimetableRow(day="Monday", start_time="09:00 AM", end_time="10:00 AM", course_name="Recovered Class"),
    ])
    monkeypatch.setattr(campus_timetable_service, "get_ai_provider", lambda: fake)

    raw_rows = _parse_csv_raw(_UNRECOGNIZABLE_CSV)
    rows = await _parse_one_sheet_async(raw_rows, use_ai_fallback=True)

    assert {r.course_name for r in rows} == {"Recovered Class"}
    assert len(rows) == 8  # 8 weeks ahead


async def test_unrecognizable_sheet_keeps_original_errors_when_ai_finds_nothing(monkeypatch):
    import app.services.campus_timetable_service as campus_timetable_service

    monkeypatch.setattr(campus_timetable_service, "get_ai_provider", lambda: _FakeProvider([]))

    raw_rows = _parse_csv_raw(_UNRECOGNIZABLE_CSV)
    rows = await _parse_one_sheet_async(raw_rows, use_ai_fallback=True)

    # AI found nothing real — the original per-row parse errors are still
    # more useful to the uploader than silently emitting zero rows.
    assert len(rows) == 2
    assert all(r.error is not None for r in rows)


async def test_ai_fallback_can_be_disabled():
    calls = []

    class _CountingProvider(_FakeProvider):
        async def extract_timetable_rows(self, raw_text: str) -> list[ExtractedTimetableRow]:
            calls.append(raw_text)
            return []

    raw_rows = _parse_csv_raw(_UNRECOGNIZABLE_CSV)
    rows = await _parse_one_sheet_async(raw_rows, use_ai_fallback=False)

    assert calls == []
    assert all(r.error is not None for r in rows)


async def test_parse_campus_rows_async_end_to_end(monkeypatch):
    import app.services.campus_timetable_service as campus_timetable_service

    fake = _FakeProvider([
        ExtractedTimetableRow(day="Friday", start_time="01:00 PM", end_time="02:00 PM", course_name="Whole File Fallback"),
    ])
    monkeypatch.setattr(campus_timetable_service, "get_ai_provider", lambda: fake)

    rows = await parse_campus_rows_async("notes.csv", _UNRECOGNIZABLE_CSV)
    assert {r.course_name for r in rows} == {"Whole File Fallback"}


def test_fallback_error_rate_threshold_is_sane():
    assert 0 < _AI_FALLBACK_ERROR_RATE < 1
