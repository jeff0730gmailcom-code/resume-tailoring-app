"""Unit tests for Jeff fake-history time tiers (no DB)."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.jeff_daily_pad import PAD_TZ, fake_target_for_local_time  # noqa: E402


def _at(weekday: int, hour: int, minute: int = 0) -> datetime:
    """Build a local PAD_TZ datetime with the given weekday (Mon=0)."""
    # 2026-03-02 is a Monday.
    monday = datetime(2026, 3, 2, hour, minute, tzinfo=PAD_TZ)
    return monday + timedelta(days=weekday)


def test_weekday_morning_target_20():
    assert fake_target_for_local_time(_at(0, 9, 0)) == 20
    assert fake_target_for_local_time(_at(2, 12, 59)) == 20


def test_weekday_afternoon_target_50():
    assert fake_target_for_local_time(_at(1, 13, 0)) == 50
    assert fake_target_for_local_time(_at(3, 15, 30)) == 50
    # 4pm–8pm holds afternoon tier
    assert fake_target_for_local_time(_at(4, 16, 0)) == 50
    assert fake_target_for_local_time(_at(4, 19, 59)) == 50


def test_weekday_evening_target_80():
    assert fake_target_for_local_time(_at(0, 20, 0)) == 80
    assert fake_target_for_local_time(_at(4, 23, 15)) == 80


def test_weekend_no_padding():
    assert fake_target_for_local_time(_at(5, 10, 0)) is None  # Saturday
    assert fake_target_for_local_time(_at(6, 21, 0)) is None  # Sunday
