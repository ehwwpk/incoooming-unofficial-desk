from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING

from schwab_dashboard.application.alerts.models import DeskAlert
from schwab_dashboard.application.alerts.rules import (
    evaluate_call_expiration_pressures,
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
        directional = list(evaluate_call_expiration_pressures(underlying))
        fast_move = evaluate_fast_move(underlying)
        if fast_move is not None:
            directional.append(fast_move)

        # Momentum and proximity can describe the same contract. Keep its clearest,
        # most urgent note, but never let that contract hide another live call.
        by_contract: dict[str, DeskAlert] = {}
        for alert in directional:
            contract_key = alert.roll_source_option_symbol or alert.alert_id
            current = by_contract.get(contract_key)
            if current is None or alert.priority > current.priority:
                by_contract[contract_key] = alert
        alerts.extend(by_contract.values())
    put_alerts_by_symbol: dict[str, list[DeskAlert]] = {}
    for put in put_positions:
        put_alert = evaluate_short_put_pressure(put)
        if put_alert is not None:
            put_alerts_by_symbol.setdefault(put_alert.symbol, []).append(put_alert)
    alerts.extend(
        max(symbol_alerts, key=lambda alert: alert.priority)
        for symbol_alerts in put_alerts_by_symbol.values()
    )
    return tuple(sorted(alerts, key=lambda alert: (-alert.priority, alert.symbol)))
