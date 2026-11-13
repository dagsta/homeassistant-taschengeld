"""Tests for the fixed-time polling schedule."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from custom_components.taschengeld.coordinator import next_slot_delay

UTC = ZoneInfo("UTC")


def _at(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2026, 11, 12, hour, minute, second, tzinfo=UTC)


@pytest.mark.parametrize(
    ("now", "start", "hours", "expected"),
    [
        # 06:00 every 8 h -> 06:00, 14:00, 22:00
        (_at(5), time(6), 8, 3600),
        (_at(6, 0, 30), time(6), 8, 8 * 3600 - 30),
        (_at(14, 30), time(6), 8, 7.5 * 3600),
        (_at(22, 30), time(6), 8, 7.5 * 3600),  # wraps over midnight to 06:00
        # once a day
        (_at(7, 30), time(7), 24, 23.5 * 3600),
        (_at(6), time(7), 24, 3600),
        # every 6 h from 07:30 -> 01:30, 07:30, 13:30, 19:30
        (_at(2), time(7, 30), 6, 5.5 * 3600),
        (_at(19, 31), time(7, 30), 6, 6 * 3600 - 60),
        # every 12 h from 00:00
        (_at(0, 0, 10), time(0), 12, 12 * 3600 - 10),
        # a slot less than a minute away is skipped (timer fired early)
        (_at(5, 59, 30), time(6), 8, 8 * 3600 + 30),
    ],
)
def test_next_slot_delay(now: datetime, start: time, hours: int, expected: float) -> None:
    """The next polling time is anchored to the start time of day."""
    assert next_slot_delay(now, start, hours) == pytest.approx(expected)


def test_slots_follow_local_time_across_dst() -> None:
    """The slot stays at the same local clock time when clocks change."""
    berlin = ZoneInfo("Europe/Berlin")
    # Clocks go back on 2026-10-25 at 03:00. From 12:00 CEST on the 24th the
    # next 07:00 local slot is 19 wall-clock hours away but 20 real hours.
    now = datetime(2026, 10, 24, 12, 0, tzinfo=berlin)
    assert next_slot_delay(now, time(7), 24) == pytest.approx(20 * 3600)
