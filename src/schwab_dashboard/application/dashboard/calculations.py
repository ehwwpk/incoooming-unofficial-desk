from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.dashboard.models import (
    AccountDayProfitLoss,
    AllocationSlice,
    PortfolioSummary,
    PositionSummary,
    RiskSummary,
)
from schwab_dashboard.application.option_lifecycle import contract_multiplier
from schwab_dashboard.application.performance.models import ReturnPoint
from schwab_dashboard.application.values import optional_bool

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
            is_non_standard=optional_bool(row.get("is_non_standard")),
            account_id=(str(row["account_id"]) if row.get("account_id") else None),
        )
        for row in rows
    )


def broker_day_profit_loss(
    positions: Sequence[PositionSummary],
    *,
    current_account_value: Decimal | None,
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
    if any(value is None for value in reported):
        return None, None
    day_profit_loss = sum((value for value in reported if value is not None), ZERO)
    if current_account_value is None:
        return day_profit_loss, None
    prior_value = current_account_value - day_profit_loss
    if prior_value == ZERO:
        return day_profit_loss, ZERO
    return day_profit_loss, day_profit_loss / prior_value * Decimal("100")


def account_day_profit_loss(
    points: Sequence[ReturnPoint],
) -> AccountDayProfitLoss:
    """Read the latest complete flow-neutral link from the managed return path.

    The homepage and Results must use the same identity.  A day is therefore
    available only when the return engine linked two consecutive aggregate
    net-liquidation snapshots with unchanged account coverage.
    """

    if len(points) < 2:
        return AccountDayProfitLoss(
            status="not_available",
            profit_loss=None,
            profit_loss_percent=None,
            external_cash_flow=ZERO,
            as_of=points[-1].date if points else None,
            previous_as_of=None,
        )
    previous, current = points[-2:]
    return_quality = current.return_quality
    session_span = current.session_span
    if return_quality == "unresolved" and current.quality in {
        "linked",
        "linked_after_incomplete_history",
    }:
        # Backward-compatible ingestion for previously materialized points.
        return_quality = "observed"
        session_span = session_span or 1
    if current.return_quality == "multi_session" and current.interval_return_percent is not None:
        return AccountDayProfitLoss(
            status="multi_session",
            profit_loss=current.value - previous.value - current.external_flow,
            profit_loss_percent=current.interval_return_percent,
            external_cash_flow=current.external_flow,
            as_of=current.date,
            previous_as_of=previous.date,
        )
    if (
        current.daily_return_percent is None
        or session_span != 1
        or return_quality not in {"observed", "derived", "estimated", "provisional"}
    ):
        return AccountDayProfitLoss(
            status=current.quality,
            profit_loss=None,
            profit_loss_percent=None,
            external_cash_flow=current.external_flow,
            as_of=current.date,
            previous_as_of=previous.date,
        )
    return AccountDayProfitLoss(
        status="linked" if return_quality == "observed" else return_quality,
        profit_loss=current.value - previous.value - current.external_flow,
        profit_loss_percent=current.daily_return_percent,
        external_cash_flow=current.external_flow,
        as_of=current.date,
        previous_as_of=previous.date,
    )


def summarize_portfolio(
    positions: Sequence[PositionSummary],
    balances: Sequence[dict[str, Any]] = (),
    *,
    account_day: AccountDayProfitLoss | None = None,
) -> PortfolioSummary:
    stock_value = _sum_complete(
        [
            position.market_value
            for position in positions
            if position.asset_type.upper() != "OPTION"
        ],
        empty=ZERO,
    )
    option_value = _sum_complete(
        [
            position.market_value
            for position in positions
            if position.asset_type.upper() == "OPTION"
        ],
        empty=ZERO,
    )
    net_position_value = (
        stock_value + option_value if stock_value is not None and option_value is not None else None
    )
    gross_position_value = _sum_complete(
        [
            abs(position.market_value) if position.market_value is not None else None
            for position in positions
        ],
        empty=ZERO,
    )
    liquidation_values = [_optional_decimal(row.get("liquidation_value")) for row in balances]
    liquidation_value = _sum_complete(liquidation_values)
    equity = _sum_complete([_optional_decimal(row.get("equity")) for row in balances])
    cash_value = _sum_complete([_optional_decimal(row.get("cash_balance")) for row in balances])
    margin_balance = _sum_complete(
        [_optional_decimal(row.get("margin_balance")) for row in balances]
    )
    buying_power = _sum_complete([_optional_decimal(row.get("buying_power")) for row in balances])
    available_funds = _sum_complete(
        [_optional_decimal(row.get("available_funds")) for row in balances]
    )
    maintenance = _sum_complete(
        [_optional_decimal(row.get("maintenance_requirement")) for row in balances]
    )
    total_value = liquidation_value if balances else net_position_value
    open_day_profit_loss, open_day_percent = broker_day_profit_loss(
        positions,
        current_account_value=total_value,
    )
    if account_day is None:
        day_profit_loss = open_day_profit_loss
        day_percent = open_day_percent
        day_flow = ZERO
        day_source = "open_positions"
        day_as_of = None
        day_previous_as_of = None
    else:
        day_profit_loss = account_day.profit_loss
        day_percent = account_day.profit_loss_percent
        day_flow = account_day.external_cash_flow
        day_source = (
            "net_liquidation"
            if account_day.status == "linked"
            else "reconstructed"
            if account_day.status in {"derived", "estimated"}
            else "provisional"
            if account_day.status == "provisional"
            else "multi_session"
            if account_day.status == "multi_session"
            else "unavailable"
        )
        day_as_of = account_day.as_of
        day_previous_as_of = account_day.previous_as_of
    reconciliation_gap = (
        open_day_profit_loss - day_profit_loss
        if open_day_profit_loss is not None and day_profit_loss is not None
        else None
    )
    if day_profit_loss is None:
        reconciliation_status = "account_day_unavailable"
    elif open_day_profit_loss is None:
        reconciliation_status = "open_positions_unavailable"
    else:
        tolerance = max(
            Decimal("5"),
            abs(total_value) * Decimal("0.0001") if total_value is not None else ZERO,
        )
        reconciliation_status = (
            "aligned" if abs(reconciliation_gap or ZERO) <= tolerance else "diverged"
        )
    return PortfolioSummary(
        total_value=total_value,
        invested_value=net_position_value,
        cash_value=cash_value,
        stock_value=stock_value,
        option_value=option_value,
        day_profit_loss=day_profit_loss,
        day_profit_loss_percent=day_percent,
        day_external_cash_flow=day_flow,
        gross_position_value=gross_position_value,
        net_position_value=net_position_value,
        liquidation_value=liquidation_value,
        equity=equity,
        margin_balance=margin_balance,
        buying_power=buying_power,
        available_funds=available_funds,
        maintenance_requirement=maintenance,
        day_profit_loss_source=day_source,
        day_profit_loss_as_of=day_as_of,
        day_profit_loss_previous_as_of=day_previous_as_of,
        open_position_day_profit_loss=open_day_profit_loss,
        open_position_day_profit_loss_percent=open_day_percent,
        day_profit_loss_reconciliation_gap=reconciliation_gap,
        day_profit_loss_reconciliation_status=reconciliation_status,
    )


def summarize_allocations(
    positions: Sequence[PositionSummary],
) -> tuple[AllocationSlice, ...]:
    if any(position.market_value is None for position in positions):
        return ()
    grouped: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
    for position in positions:
        assert position.market_value is not None
        grouped[position.asset_type.upper()] += abs(position.market_value)
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
    values_complete = all(position.market_value is not None for position in positions)
    absolute_values = [
        abs(position.market_value) for position in positions if position.market_value is not None
    ]
    gross_value = sum(absolute_values, ZERO) if values_complete else None
    largest = max(absolute_values, default=ZERO) if values_complete else None
    return RiskSummary(
        buying_power_used_percent=None,
        portfolio_delta=None,
        daily_theta=None if option_positions else ZERO,
        short_contracts=sum(
            int(abs(position.quantity)) for position in option_positions if position.quantity < ZERO
        ),
        next_expiration=None,
        largest_position_percent=(
            largest / gross_value * 100
            if largest is not None and gross_value
            else ZERO
            if gross_value == ZERO
            else None
        ),
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


def _sum_complete(
    values: Sequence[Decimal | None],
    *,
    empty: Decimal | None = None,
) -> Decimal | None:
    if not values:
        return empty
    if any(value is None for value in values):
        return None
    return sum((value for value in values if value is not None), ZERO)


def _position_mark(row: dict[str, Any]) -> Decimal | None:
    market_value = _optional_decimal(row.get("market_value"))
    quantity = abs(_decimal(row.get("net_quantity")))
    if market_value is None or not quantity:
        return None
    if str(row.get("asset_type", "")).upper() == "OPTION":
        if (
            row.get("contract_multiplier") is None
            and row.get("multiplier") is None
            and row.get("is_non_standard") is not False
        ):
            return None
        multiplier = contract_multiplier(row)
    else:
        multiplier = Decimal("1")
    if multiplier <= ZERO:
        return None
    return abs(market_value) / quantity / multiplier


def _strategy(row: dict[str, Any]) -> str | None:
    if str(row.get("asset_type", "")).upper() != "OPTION":
        return None
    side = "Short" if _decimal(row.get("net_quantity")) < ZERO else "Long"
    option_type = str(row.get("option_type") or "option").lower()
    return f"{side} {option_type}"
