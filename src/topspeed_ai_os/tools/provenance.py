"""Validation for Source-owned temporal provenance."""

from __future__ import annotations

from datetime import datetime


def parse_source_data_as_of(value: str) -> datetime:
    """Parse an explicit Source timestamp without inventing a fallback value."""

    if not isinstance(value, str) or not value:
        raise ValueError("Source data_as_of must be a non-empty ISO 8601 string")
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("Source data_as_of is not valid ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Source data_as_of must be timezone-aware")
    return parsed
