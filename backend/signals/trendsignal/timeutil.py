"""Date helpers. Everything is stored as timezone-aware UTC ISO-8601 strings."""

from __future__ import annotations

import calendar
import time
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc


def now_utc() -> datetime:
    return datetime.now(UTC)


def to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="seconds")


def parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_any(value: object) -> datetime | None:
    """Parse the date shapes sources send: ISO strings, epoch seconds, or struct_time."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, time.struct_time):
        return datetime.fromtimestamp(calendar.timegm(value), UTC)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), UTC)
    if isinstance(value, str):
        try:
            return parse_iso(value.strip())
        except ValueError:
            return None
    return None


def hours_between(earlier: datetime, later: datetime) -> float:
    return max(0.0, (later - earlier).total_seconds() / 3600.0)


def local_date(value: datetime, tz_name: str) -> date:
    return value.astimezone(ZoneInfo(tz_name)).date()


def local_day_start(value: datetime, tz_name: str) -> datetime:
    """Midnight of `value`'s local calendar day, returned in UTC."""
    local = value.astimezone(ZoneInfo(tz_name))
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
