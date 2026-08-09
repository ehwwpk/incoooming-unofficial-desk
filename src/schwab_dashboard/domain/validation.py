from __future__ import annotations

from datetime import datetime
from decimal import Decimal


def require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")


def require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")


def require_non_negative(value: Decimal, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def require_optional_non_negative(value: Decimal | None, field_name: str) -> None:
    if value is not None:
        require_non_negative(value, field_name)
