from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.performance.models import CapitalEfficiency, ReturnPoint

ZERO = Decimal("0")
HUNDRED = Decimal("100")
_QUALITY_RANK = {"observed": 0, "derived": 1, "estimated": 2, "unresolved": 3}


def calculate_capital_efficiency(
    *,
    actual_points: Sequence[ReturnPoint],
    balance_history: Sequence[dict[str, Any]],
    net_option_cash: Decimal,
) -> CapitalEfficiency:
    valued_points = tuple(point for point in actual_points if point.value > ZERO)
    values = [point.value for point in valued_points]
    average = sum(values, ZERO) / Decimal(len(values)) if values else None
    qualities = tuple(_value_quality(point) for point in valued_points)
    counts = {quality: qualities.count(quality) for quality in _QUALITY_RANK}
    quality = max(
        qualities or ("unresolved",),
        key=lambda item: _QUALITY_RANK.get(item, _QUALITY_RANK["unresolved"]),
    )
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
            "Option cash divided by average best-available session net liquidation is a "
            "capital-use ratio, not a portfolio return. The average includes "
            f"{counts['observed']} observed, {counts['derived']} reconstructed, "
            f"{counts['estimated']} estimated, and {counts['unresolved']} unresolved session "
            "value(s). Account maintenance includes the whole broker account."
        ),
        quality=quality,
        observed_sessions=counts["observed"],
        derived_sessions=counts["derived"],
        estimated_sessions=counts["estimated"],
        unresolved_sessions=counts["unresolved"],
    )


def _value_quality(point: ReturnPoint) -> str:
    if point.value_quality in {"observed", "derived", "estimated"}:
        return point.value_quality
    legacy = point.quality.casefold()
    if "estimated" in legacy or "carried" in legacy:
        return "estimated"
    if "derived" in legacy or "price_only" in legacy:
        return "derived"
    if legacy in {"observed", "observed_anchor", "linked"}:
        return "observed"
    return "unresolved"


def _latest_account_rows(rows: Sequence[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        account = str(row.get("account_id") or row.get("account_mask") or "ACCOUNT")
        observed = row.get("observed_at")
        previous = latest.get(account)
        if (
            previous is None
            or previous.get("observed_at") is None
            or (observed is not None and _timestamp(observed) > _timestamp(previous["observed_at"]))
        ):
            latest[account] = row
    return tuple(latest.values())


def _sum_optional(rows: Sequence[dict[str, Any]], key: str) -> Decimal | None:
    if not rows or any(row.get(key) is None for row in rows):
        return None
    return sum((Decimal(str(row[key])) for row in rows), ZERO)


def _timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    return datetime.min.replace(tzinfo=UTC)
