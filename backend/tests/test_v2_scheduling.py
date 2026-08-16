from datetime import datetime, timezone

import pytest

from app.services.exam_scheduler_service import _slot_minutes
from app.services.registration_service import next_thursday_ist, registration_is_open


def test_registration_is_open_only_on_thursday_ist():
    wed = datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc)
    thu = datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)
    fri = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)

    assert registration_is_open(wed) is False
    assert registration_is_open(thu) is True
    assert registration_is_open(fri) is False


def test_next_thursday_ist_rolls_forward_from_friday():
    friday = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)
    next_open = next_thursday_ist(friday)

    assert next_open.isoformat().startswith("2026-08-20T00:00:00")


def test_next_thursday_ist_keeps_current_thursday_when_open():
    thursday = datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)
    next_open = next_thursday_ist(thursday)

    assert next_open.isoformat().startswith("2026-08-13T00:00:00")


@pytest.mark.parametrize("slot", ["00:00", "09:30", "23:59"])
def test_exam_time_slots_parse(slot):
    assert _slot_minutes(slot)[0] >= 0


def test_exam_time_slot_rejects_invalid_values():
    with pytest.raises(ValueError):
        _slot_minutes("25:00")
    with pytest.raises(ValueError):
        _slot_minutes("09:77")
