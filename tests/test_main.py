"""Maintenance-window guard tests."""

from datetime import datetime
from zoneinfo import ZoneInfo

from src.main import in_maintenance_window

ET = ZoneInfo("America/New_York")


def test_inside_window():
    # 4 AM ET -> inside 3-5 AM maintenance
    assert in_maintenance_window(datetime(2026, 11, 15, 4, 0, tzinfo=ET))


def test_boundaries():
    # 3:00 sharp IS inside (>= start), 5:00 sharp is NOT (< end fails)
    assert in_maintenance_window(datetime(2026, 11, 15, 3, 0, tzinfo=ET))
    assert not in_maintenance_window(datetime(2026, 11, 15, 5, 0, tzinfo=ET))
    assert not in_maintenance_window(datetime(2026, 11, 15, 2, 59, tzinfo=ET))


def test_outside_window():
    assert not in_maintenance_window(datetime(2026, 11, 15, 14, 0, tzinfo=ET))
    # tz-aware UTC input converted to ET: 18:00 UTC = 13:00 EST -> outside
    from datetime import timezone
    assert not in_maintenance_window(datetime(2026, 11, 15, 18, 0, tzinfo=timezone.utc))
    # 08:00 UTC = 03:00 EST -> inside (DST handled by zoneinfo)
    assert in_maintenance_window(datetime(2026, 11, 15, 8, 0, tzinfo=timezone.utc))
