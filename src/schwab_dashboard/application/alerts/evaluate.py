from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from schwab_dashboard.application.alerts.models import DeskAlert
from schwab_dashboard.application.alerts.rules import (
    evaluate_dividend_overlap,
    evaluate_fast_move,
)
from schwab_dashboard.application.dashboard.covered_calls import UnderlyingCallStats


def build_desk_alerts(
    underlyings: Sequence[UnderlyingCallStats],
    *,
    as_of: date,
) -> tuple[DeskAlert, ...]:
    alerts = [
        alert
        for underlying in underlyings
        for alert in (
            evaluate_dividend_overlap(underlying, as_of=as_of),
            evaluate_fast_move(underlying),
        )
        if alert is not None
    ]
    return tuple(sorted(alerts, key=lambda alert: (-alert.priority, alert.symbol)))
