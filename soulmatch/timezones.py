"""Module 18 — timezone display helpers (V3-6-2).

Storage stays UTC everywhere (SQLAlchemy DateTime columns; SQLite drops
tzinfo on round-trip, same as billing.py's plan_grace_until — see the note
there) — this module ONLY affects how a datetime is *displayed* to a given
member, never how it's stored, compared, or queried.
"""

from __future__ import annotations

from datetime import datetime, timezone as _tz
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Asia/Kolkata"

# A short curated list for the My Plan picker, not the full ~600-zone IANA
# database — these cover India plus the NRI geographies V3_PLAN.md's Part 3
# GTM targets (US, Singapore, Gulf, UK, Australia).
COMMON_TIMEZONES = [
    "Asia/Kolkata",
    "Asia/Dubai",
    "Asia/Singapore",
    "Asia/Riyadh",
    "America/New_York",
    "America/Chicago",
    "America/Los_Angeles",
    "Europe/London",
    "Australia/Sydney",
]


def to_local(dt: datetime | None, tz_name: str | None) -> datetime | None:
    """Convert a stored datetime (naive or UTC-aware) to the given IANA
    zone for display. None passes through unchanged. An unknown zone name
    falls back to DEFAULT_TIMEZONE rather than raising — this only affects
    display, never anything load-bearing."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tz.utc)
    try:
        zone = ZoneInfo(tz_name or DEFAULT_TIMEZONE)
    except Exception:
        zone = ZoneInfo(DEFAULT_TIMEZONE)
    return dt.astimezone(zone)
