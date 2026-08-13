from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING

from schwab_dashboard.application.alerts.models import DeskAlert
from schwab_dashboard.application.alerts.rules import (
    evaluate_call_expiration_pressure,
    evaluate_dividend_overlap,
    evaluate_fast_move,
    evaluate_short_put_pressure,
)
from schwab_dashboard.application.dashboard.covered_calls import UnderlyingCallStats

if TYPE_CHECKING:
    from schwab_dashboard.application.dashboard.models import LiveOpenOptionPosition


def build_desk_alerts(
    underlyings: Sequence[UnderlyingCallStats],
    *,
    as_of: date,
    put_positions: Sequence[LiveOpenOptionPosition] = (),
) -> tuple[DeskAlert, ...]:
    alerts: list[DeskAlert] = []
    for underlying in underlyings:
        dividend = evaluate_dividend_overlap(underlying, as_of=as_of)
        if dividend is not None:
            alerts.append(dividend)
        directional = tuple(
            alert
            for alert in (
                evaluate_fast_move(underlying),
                evaluate_call_expiration_pressure(underlying),
            )
            if alert is not None
        )
        if directional:
            alerts.append(max(directional, key=lambda alert: alert.priority))
    put_alerts_by_symbol: dict[str, list[DeskAlert]] = {}
    for put in put_positions:
        alert = evaluate_short_put_pressure(put)
        if alert is not None:
            put_alerts_by_symbol.setdefault(alert.symbol, []).append(alert)
    alerts.extend(
        max(symbol_alerts, key=lambda alert: alert.priority)
        for symbol_alerts in put_alerts_by_symbol.values()
    )
    return tuple(sorted(alerts, key=lambda alert: (-alert.priority, alert.symbol)))
