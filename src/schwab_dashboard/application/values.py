from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal


def optional_bool(value: object) -> bool | None:
    """Parse common persisted boolean forms without treating text as truthy."""

    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    return None


def sum_if_complete(values: Iterable[Decimal | None]) -> Decimal | None:
    """Sum values only when every component is known.

    An empty collection is a real zero. A collection containing an unknown value
    is unknown; silently dropping that component would publish a partial total as
    though it were complete.
    """

    total = Decimal("0")
    for value in values:
        if value is None:
            return None
        total += value
    return total
