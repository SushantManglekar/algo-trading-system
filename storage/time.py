"""Database timestamp normalization at persistence boundaries."""

from __future__ import annotations

from datetime import UTC, datetime


def as_utc(value: datetime) -> datetime:
    """Return UTC-aware timestamps, including SQLite values that lose tzinfo on round-trip."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
