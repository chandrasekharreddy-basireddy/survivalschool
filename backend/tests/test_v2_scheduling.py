from datetime import datetime, timezone

import pytest

from app.services.exam_scheduler_service import _slot_minutes
from app.services.registration_service import next_registration_open_ist, registration_is_open


def test_registration_is_closed_on_thursday_ist():
    wed = datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc)
    thu = datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)
    fri = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)

    assert registration_is_open(wed) is True
    assert registration_is_open(thu) is False
    assert registration_is_open(fri) is True


def test_next_registration_open_skips_thursday():
    thursday = datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)
    next_open = next_registration_open_ist(thursday)
    assert next_open.isoformat().startswith("2026-08-14T00:00:00")


def test_next_registration_open_rolls_to_next_day_after_end_of_day():
    friday = datetime(2026, 8, 14, 23, 59, 59, tzinfo=timezone.utc)
    next_open = next_registration_open_ist(friday)
    assert next_open.isoformat().startswith("2026-08-15T00:00:00")


@pytest.mark.parametrize("slot", ["00:00", "09:30", "23:59"])
def test_exam_time_slots_parse(slot):
    assert _slot_minutes(slot)[0] >= 0


def test_exam_time_slot_rejects_invalid_values():
    with pytest.raises(ValueError):
        _slot_minutes("25:00")
    with pytest.raises(ValueError):
        _slot_minutes("09:77")
