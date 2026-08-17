from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.performance.models import CapitalEfficiency, ReturnPoint

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def calculate_capital_efficiency(
    *,
    actual_points: Sequence[ReturnPoint],
    balance_history: Sequence[dict[str, Any]],
    net_option_cash: Decimal,
) -> CapitalEfficiency:
    values = [point.value for point in actual_points if point.value > ZERO]
    average = sum(values, ZERO) / Decimal(len(values)) if values else None
    latest_rows = _latest_account_rows(balance_history)
    latest_net_liquidation = _sum_optional(latest_rows, "liquidation_value")
    maintenance = _sum_optional(latest_rows, "maintenance_requirement")
    buying_power = _sum_optional(latest_rows, "buying_power")
    available_funds = _sum_optional(latest_rows, "available_funds")
    return CapitalEfficiency(
        status="ready" if average is not None else "waiting",
        average_net_liquidation=average,
        latest_net_liquidation=latest_net_liquidation,
        option_cash_on_average_capital_percent=(
            net_option_cash / average * HUNDRED if average else None
        ),
        maintenance_requirement=maintenance,
        maintenance_to_net_liquidation_percent=(
            maintenance / latest_net_liquidation * HUNDRED
            if maintenance is not None and latest_net_liquidation
            else None
        ),
        buying_power=buying_power,
        available_funds=available_funds,
        method_note=(
            "Option cash divided by average observed net liquidation is a capital-use ratio, "
            "not a portfolio return. Account maintenance includes the whole broker account."
        ),
    )


def _latest_account_rows(rows: Sequence[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        account = str(row.get("account_mask") or "ACCOUNT")
        observed = row.get("observed_at")
        previous = latest.get(account)
        if previous is None or previous.get("observed_at") is None or (
            observed is not None and observed > previous["observed_at"]
        ):
            latest[account] = row
    return tuple(latest.values())


def _sum_optional(rows: Sequence[dict[str, Any]], key: str) -> Decimal | None:
    values = [Decimal(str(row[key])) for row in rows if row.get(key) is not None]
    return sum(values, ZERO) if values else None
