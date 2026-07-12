from datetime import datetime, timezone

from soulmatch import timezones as tz


def test_to_local_converts_naive_utc():
    naive_utc = datetime(2026, 1, 1, 0, 0, 0)  # midnight UTC
    local = tz.to_local(naive_utc, "America/New_York")
    # UTC-5 in January (no DST) -> previous day, 19:00
    assert local.year == 2025 and local.month == 12 and local.day == 31
    assert local.hour == 19


def test_to_local_converts_aware_utc():
    aware_utc = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    local = tz.to_local(aware_utc, "Asia/Kolkata")
    # UTC+5:30
    assert local.hour == 5 and local.minute == 30


def test_to_local_passes_none_through():
    assert tz.to_local(None, "Asia/Kolkata") is None


def test_to_local_defaults_when_tz_name_is_none():
    naive_utc = datetime(2026, 1, 1, 0, 0, 0)
    local = tz.to_local(naive_utc, None)
    default_local = tz.to_local(naive_utc, tz.DEFAULT_TIMEZONE)
    assert local == default_local


def test_to_local_falls_back_on_unknown_zone():
    naive_utc = datetime(2026, 1, 1, 0, 0, 0)
    local = tz.to_local(naive_utc, "Not/A_Real_Zone")
    default_local = tz.to_local(naive_utc, tz.DEFAULT_TIMEZONE)
    assert local == default_local


def test_common_timezones_are_all_valid():
    from zoneinfo import ZoneInfo
    for name in tz.COMMON_TIMEZONES:
        ZoneInfo(name)  # raises if invalid
