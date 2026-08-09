from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from schwab_dashboard.application.errors import SourceRecordConflictError


def ensure_immutable_match(
    row: object,
    expected: dict[str, Any],
    *,
    identity: str,
) -> None:
    mismatches = [
        field
        for field, expected_value in expected.items()
        if not _equivalent(getattr(row, field), expected_value)
    ]
    if mismatches:
        fields = ", ".join(sorted(mismatches))
        raise SourceRecordConflictError(
            f"Source identity {identity} was reused with different immutable fields: {fields}"
        )


def _equivalent(actual: Any, expected: Any) -> bool:
    if isinstance(actual, datetime) and isinstance(expected, datetime):
        return _utc(actual) == _utc(expected)
    return bool(actual == expected)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
