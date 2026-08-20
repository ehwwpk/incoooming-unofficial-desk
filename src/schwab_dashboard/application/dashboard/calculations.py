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

ZERO = Decimal("0")
OPTION_DAY_PERCENT_MARK_FLOOR = Decimal("0.50")


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
            contract_multiplier=_optional_decimal(row.get("contract_multiplier")),
            multiplier_source=(
                str(row["multiplier_source"]) if row.get("multiplier_source") else None
            ),
        )
        for row in rows
    )


def broker_day_profit_loss(
    positions: Sequence[PositionSummary],
    *,
    current_account_value: Decimal,
) -> tuple[Decimal | None, Decimal | None]:
    """Schwab-style session P/L for the whole book.

    Sums every position's broker day dollars regardless of asset type. Does
    not use account start-of-day liquidation, local calendar dates, or quote
    previous-close math. Percent is dollars over implied prior account value
    (current minus the tape), matching Schwab mobile Day Change.
    """

    if not positions:
        return ZERO, ZERO
    reported = tuple(position.day_profit_loss for position in positions)
    if all(value is None for value in reported):
        return None, None
    day_profit_loss = sum((value or ZERO for value in reported), ZERO)
    prior_value = current_account_value - day_profit_loss
    if prior_value == ZERO:
        return day_profit_loss, ZERO
    return day_profit_loss, day_profit_loss / prior_value * Decimal("100")


def summarize_portfolio(
    positions: Sequence[PositionSummary],
    balances: Sequence[dict[str, Any]] = (),
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
    day_profit_loss, day_percent = broker_day_profit_loss(
        positions,
        current_account_value=total_value,
    )
    return PortfolioSummary(
        total_value=total_value,
        invested_value=net_position_value,
        cash_value=cash_value or ZERO,
        stock_value=stock_value,
        option_value=option_value,
        day_profit_loss=day_profit_loss,
        day_profit_loss_percent=day_percent,
        day_external_cash_flow=ZERO,
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


def displayed_day_profit_loss_percent(position: PositionSummary) -> Decimal | None:
    """Return the row day-% that is safe to print next to broker day dollars.

    Schwab stores currentDayProfitLossPercentage as-is. On a near-worthless
    option mark that figure is not a meaningful move. Equities keep the broker
    percent. The snapshot field itself is not changed.
    """

    if str(position.asset_type).upper() == "OPTION" and (
        position.mark is None or position.mark < OPTION_DAY_PERCENT_MARK_FLOOR
    ):
        return None
    return position.day_profit_loss_percent


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
