from __future__ import annotations

from decimal import Decimal
from hashlib import sha256

from schwab_dashboard.application.alerts.models import AlertLevel


def option_alert_id(
    *,
    symbol: str,
    reason: str,
    contract_key: str,
    level: AlertLevel,
    strike_distance_percent: Decimal,
    days_to_expiration: int,
    event_key: str = "",
) -> str:
    """Identify a material alert state without making unchanged notes new each day."""

    state = "|".join(
        (
            symbol.upper(),
            reason,
            contract_key,
            level.value,
            _distance_band(strike_distance_percent),
            _time_band(days_to_expiration),
            event_key,
        )
    )
    digest = sha256(state.encode("utf-8")).hexdigest()[:10]
    return f"{symbol.lower()}-{reason}-{digest}"


def _distance_band(value: Decimal) -> str:
    if value <= 0:
        return "itm"
    if value <= Decimal("3"):
        return "within-3"
    if value <= Decimal("7"):
        return "within-7"
    if value <= Decimal("15"):
        return "within-15"
    return "outside-15"


def _time_band(days: int) -> str:
    if days <= 2:
        return "0-2"
    if days <= 7:
        return "3-7"
    if days <= 14:
        return "8-14"
    if days <= 30:
        return "15-30"
    return "31-plus"
