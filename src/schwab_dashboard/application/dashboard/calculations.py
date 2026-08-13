from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.dashboard.models import (
    AllocationSlice,
    PortfolioSummary,
    PositionSummary,
    RiskSummary,
)
from schwab_dashboard.application.market_time import market_date

ZERO = Decimal("0")


def map_positions(rows: Sequence[dict[str, Any]]) -> tuple[PositionSummary, ...]:
    return tuple(
        PositionSummary(
            account_mask=str(row["account_mask"]),
            symbol=str(row["symbol"]),
            description=(
                str(row.get("description") or "").strip()
                or str(row["asset_type"]).replace("_", " ").title()
            ),
            asset_type=str(row["asset_type"]),
            quantity=_decimal(row.get("net_quantity")),
            average_price=_optional_decimal(row.get("average_price")),
            mark=_position_mark(row),
            market_value=_optional_decimal(row.get("market_value")),
            day_profit_loss=_optional_decimal(row.get("day_profit_loss")),
            day_profit_loss_percent=_optional_decimal(row.get("day_profit_loss_percent")),
            strategy=_strategy(row),
            underlying_symbol=(
                str(row["underlying_symbol"]) if row.get("underlying_symbol") else None
            ),
            option_type=(str(row["option_type"]) if row.get("option_type") else None),
            expiration_date=_optional_date(row.get("expiration_date")),
            strike=_optional_decimal(row.get("strike")),
            open_profit_loss=_optional_decimal(
                row.get("short_open_profit_loss")
                if _decimal(row.get("short_quantity")) > ZERO
                else row.get("long_open_profit_loss")
            ),
        )
        for row in rows
    )


def summarize_portfolio(
    positions: Sequence[PositionSummary],
    balances: Sequence[dict[str, Any]] = (),
    *,
    cash_movements: Sequence[dict[str, Any]] = (),
    as_of: date | datetime | None = None,
) -> PortfolioSummary:
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
    net_position_value = stock_value + option_value
    gross_position_value = sum((abs(position.market_value or ZERO) for position in positions), ZERO)
    liquidation_values = [_optional_decimal(row.get("liquidation_value")) for row in balances]
    liquidation_value = _sum_known(liquidation_values)
    day_balance_pairs = [
        (
            _optional_decimal(row.get("liquidation_value")),
            _optional_decimal(row.get("initial_liquidation_value")),
        )
        for row in balances
    ]
    equity = _sum_known([_optional_decimal(row.get("equity")) for row in balances])
    cash_value = _sum_known([_optional_decimal(row.get("cash_balance")) for row in balances])
    margin_balance = _sum_known([_optional_decimal(row.get("margin_balance")) for row in balances])
    buying_power = _sum_known([_optional_decimal(row.get("buying_power")) for row in balances])
    available_funds = _sum_known(
        [_optional_decimal(row.get("available_funds")) for row in balances]
    )
    maintenance = _sum_known(
        [_optional_decimal(row.get("maintenance_requirement")) for row in balances]
    )
    total_value = liquidation_value if liquidation_value is not None else net_position_value
    day_external_cash_flow = ZERO
    if day_balance_pairs and all(
        current is not None and initial is not None
        for current, initial in day_balance_pairs
    ):
        current_day_value = sum(
            (current for current, _ in day_balance_pairs if current is not None), ZERO
        )
        prior_value = sum(
            (initial for _, initial in day_balance_pairs if initial is not None), ZERO
        )
        day_external_cash_flow = _daily_external_cash_flow(cash_movements, as_of=as_of)
        day_profit_loss = current_day_value - prior_value - day_external_cash_flow
    else:
        day_profit_loss = sum(
            ((position.day_profit_loss or ZERO) for position in positions), ZERO
        )
        prior_value = total_value - day_profit_loss
    day_percent = day_profit_loss / prior_value * 100 if prior_value else ZERO
    return PortfolioSummary(
        total_value=total_value,
        invested_value=net_position_value,
        cash_value=cash_value or ZERO,
        stock_value=stock_value,
        option_value=option_value,
        day_profit_loss=day_profit_loss,
        day_profit_loss_percent=day_percent,
        day_external_cash_flow=day_external_cash_flow,
        gross_position_value=gross_position_value,
        net_position_value=net_position_value,
        liquidation_value=liquidation_value,
        equity=equity,
        margin_balance=margin_balance,
        buying_power=buying_power,
        available_funds=available_funds,
        maintenance_requirement=maintenance,
    )


def summarize_allocations(
    positions: Sequence[PositionSummary],
) -> tuple[AllocationSlice, ...]:
    grouped: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
    for position in positions:
        grouped[position.asset_type.upper()] += abs(position.market_value or ZERO)
    total = sum(grouped.values(), ZERO)
    tones = ("gold", "emerald", "olive", "green")
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


def _optional_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _sum_known(values: Sequence[Decimal | None]) -> Decimal | None:
    known = [value for value in values if value is not None]
    return sum(known, ZERO) if known else None


def _daily_external_cash_flow(
    cash_movements: Sequence[dict[str, Any]],
    *,
    as_of: date | datetime | None,
) -> Decimal:
    """Return net deposits/withdrawals that must not be called market profit."""
    if as_of is None:
        return ZERO
    market_day = market_date(as_of)
    return sum(
        (
            _decimal(movement.get("amount"))
            for movement in cash_movements
            if str(movement.get("movement_type") or "").lower() == "transfer"
            and _market_date_or_none(movement.get("occurred_at")) == market_day
        ),
        ZERO,
    )


def _market_date_or_none(value: Any) -> date | None:
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


def _position_mark(row: dict[str, Any]) -> Decimal | None:
    market_value = _optional_decimal(row.get("market_value"))
    quantity = abs(_decimal(row.get("net_quantity")))
    if market_value is None or not quantity:
        return None
    multiplier = (
        Decimal("100") if str(row.get("asset_type", "")).upper() == "OPTION" else Decimal("1")
    )
    return abs(market_value) / quantity / multiplier


def _strategy(row: dict[str, Any]) -> str | None:
    if str(row.get("asset_type", "")).upper() != "OPTION":
        return None
    side = "Short" if _decimal(row.get("net_quantity")) < ZERO else "Long"
    option_type = str(row.get("option_type") or "option").lower()
    return f"{side} {option_type}"
