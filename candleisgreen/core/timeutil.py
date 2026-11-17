"""UTC rules.

1. Every stored or exchanged datetime is timezone-aware UTC. Naive datetimes are rejected.
2. Persistent stores hold timestamps as int64 microseconds since the Unix epoch, UTC.
3. Local market times (for example the 16:30 ET decision time) are converted with the
   IANA zone database, so daylight-saving boundaries are handled by the zone, not by code.
4. `utc_now` is the only function that reads the wall clock. Pipelines take a clock argument.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class NaiveDatetimeError(ValueError):
    """Raised when a datetime without a timezone reaches a contract boundary."""


class InvalidLocalTimeError(ValueError):
    """Raised for a local time that does not exist or is ambiguous on that date."""


def ensure_utc(dt: datetime) -> datetime:
    if not isinstance(dt, datetime):
        raise TypeError(f"expected datetime, got {type(dt).__name__}")
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise NaiveDatetimeError("naive datetime rejected. All times must carry a timezone")
    return dt.astimezone(UTC)


def to_micros(dt: datetime) -> int:
    delta = ensure_utc(dt) - _EPOCH
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


def from_micros(us: int) -> datetime:
    return _EPOCH + timedelta(microseconds=int(us))


def iso_utc(dt: datetime) -> str:
    """Canonical text form used in hashes: 2026-11-16T21:30:00.000000Z."""
    return ensure_utc(dt).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def local_to_utc(day: date, hhmm: str, tz: str) -> datetime:
    """Convert a local wall-clock time on a date to UTC. Rejects gaps and overlaps."""
    hour, minute = (int(part) for part in hhmm.split(":"))
    zone = ZoneInfo(tz)
    first = datetime.combine(day, time(hour, minute), tzinfo=zone)
    second = first.replace(fold=1)
    if first.utcoffset() != second.utcoffset():
        raise InvalidLocalTimeError(f"{day} {hhmm} {tz} is ambiguous or does not exist")
    back = first.astimezone(UTC).astimezone(zone)
    if (back.hour, back.minute) != (hour, minute):
        raise InvalidLocalTimeError(f"{day} {hhmm} {tz} does not exist")
    return first.astimezone(UTC)


def utc_now() -> datetime:
    return datetime.now(UTC)
