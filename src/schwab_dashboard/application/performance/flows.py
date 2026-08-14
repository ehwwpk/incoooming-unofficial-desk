from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.dashboard.models import PositionSummary
from schwab_dashboard.application.market_time import market_date

ZERO = Decimal("0")


def external_flow_on(
    cash_movements: Sequence[dict[str, Any]],
    day: date,
) -> Decimal:
    """Net owner contributions and withdrawals on one market date."""
    return sum(
        (
            _decimal(movement.get("amount"))
            for movement in cash_movements
            if str(movement.get("movement_type") or "").lower() == "transfer"
            and movement_date(movement.get("occurred_at")) == day
        ),
        ZERO,
    )


def carried_external_flow(
    cash_movements: Sequence[dict[str, Any]],
    *,
    as_of: date | datetime | None,
    account_day_change: Decimal,
    positions: Sequence[PositionSummary],
) -> Decimal:
    """Carry a recent transfer only while Schwab's opening baseline is stale."""
    if as_of is None or not positions or any(
        position.day_profit_loss is None for position in positions
    ):
        return ZERO
    market_day = market_date(as_of)
    earliest_day = market_day - timedelta(days=4)
    recent_prior_flow = sum(
        (
            _decimal(movement.get("amount"))
            for movement in cash_movements
            if str(movement.get("movement_type") or "").lower() == "transfer"
            and (movement_day := movement_date(movement.get("occurred_at"))) is not None
            and earliest_day <= movement_day < market_day
        ),
        ZERO,
    )
    if recent_prior_flow == ZERO:
        return ZERO
    reported_position_change = sum(
        (position.day_profit_loss or ZERO for position in positions), ZERO
    )
    unadjusted_gap = abs(account_day_change - reported_position_change)
    adjusted_gap = abs(account_day_change - recent_prior_flow - reported_position_change)
    material_improvement = max(Decimal("1"), abs(recent_prior_flow) * Decimal("0.50"))
    if adjusted_gap < unadjusted_gap and unadjusted_gap - adjusted_gap >= material_improvement:
        return recent_prior_flow
    return ZERO


def movement_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return market_date(value)
    text = str(value).strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        return market_date(datetime.fromisoformat(text))
    except ValueError:
        return date.fromisoformat(text)


def _decimal(value: Any) -> Decimal:
    return ZERO if value is None else Decimal(str(value))
