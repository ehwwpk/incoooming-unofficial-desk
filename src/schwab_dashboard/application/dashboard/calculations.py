from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.dashboard.models import (
    AllocationSlice,
    PortfolioSummary,
    PositionSummary,
    RiskSummary,
)

ZERO = Decimal("0")


def map_positions(rows: Sequence[dict[str, Any]]) -> tuple[PositionSummary, ...]:
    return tuple(
        PositionSummary(
            account_mask=str(row["account_mask"]),
            symbol=str(row["symbol"]),
            description=str(row["asset_type"]).replace("_", " ").title(),
            asset_type=str(row["asset_type"]),
            quantity=_decimal(row.get("net_quantity")),
            average_price=_optional_decimal(row.get("average_price")),
            mark=None,
            market_value=_optional_decimal(row.get("market_value")),
            day_profit_loss=_optional_decimal(row.get("day_profit_loss")),
            day_profit_loss_percent=_optional_decimal(row.get("day_profit_loss_percent")),
            strategy=None,
        )
        for row in rows
    )


def summarize_portfolio(positions: Sequence[PositionSummary]) -> PortfolioSummary:
    stock_value = sum(
        (
            (position.market_value or ZERO)
            for position in positions
            if position.asset_type.upper() != "OPTION"
        ),
        ZERO,
    )
    option_value = sum(
        (
            (position.market_value or ZERO)
            for position in positions
            if position.asset_type.upper() == "OPTION"
        ),
        ZERO,
    )
    invested_value = stock_value + option_value
    day_profit_loss = sum(((position.day_profit_loss or ZERO) for position in positions), ZERO)
    prior_value = invested_value - day_profit_loss
    day_percent = day_profit_loss / prior_value * 100 if prior_value else ZERO
    return PortfolioSummary(
        total_value=invested_value,
        invested_value=invested_value,
        cash_value=ZERO,
        stock_value=stock_value,
        option_value=option_value,
        day_profit_loss=day_profit_loss,
        day_profit_loss_percent=day_percent,
    )


def summarize_allocations(
    positions: Sequence[PositionSummary],
) -> tuple[AllocationSlice, ...]:
    grouped: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
    for position in positions:
        grouped[position.asset_type.upper()] += abs(position.market_value or ZERO)
    total = sum(grouped.values(), ZERO)
    tones = ("blue", "violet", "green", "amber")
    return tuple(
        AllocationSlice(
            label=label.replace("_", " ").title(),
            value=value,
            percent=value / total * 100 if total else ZERO,
            tone=tones[index % len(tones)],
        )
        for index, (label, value) in enumerate(
            sorted(grouped.items(), key=lambda item: item[1], reverse=True)
        )
    )


def summarize_risk(positions: Sequence[PositionSummary]) -> RiskSummary:
    option_positions = [
        position for position in positions if position.asset_type.upper() == "OPTION"
    ]
    absolute_values = [abs(position.market_value or ZERO) for position in positions]
    gross_value = sum(absolute_values, ZERO)
    largest = max(absolute_values, default=ZERO)
    return RiskSummary(
        buying_power_used_percent=ZERO,
        portfolio_delta=ZERO,
        daily_theta=ZERO,
        short_contracts=sum(
            int(abs(position.quantity)) for position in option_positions if position.quantity < ZERO
        ),
        next_expiration=None,
        largest_position_percent=largest / gross_value * 100 if gross_value else ZERO,
        open_campaigns=0,
    )


def _decimal(value: Any) -> Decimal:
    return ZERO if value is None else Decimal(str(value))


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))
