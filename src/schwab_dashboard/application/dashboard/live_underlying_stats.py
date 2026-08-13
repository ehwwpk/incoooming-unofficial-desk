from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import (
    PricePoint,
    UnderlyingCallStats,
    UnderlyingPerformanceWindow,
)
from schwab_dashboard.application.dashboard.live_chart_history import (
    build_option_events,
    build_price_points,
    build_share_trade_events,
)
from schwab_dashboard.application.dashboard.live_option_clocks import (
    build_open_call_clocks,
)
from schwab_dashboard.application.dashboard.models import (
    LivePositionBook,
    LiveUnderlyingPosition,
    PositionSummary,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")
YEAR_DAYS = Decimal("365")
TONE_CYCLE = ("gold", "emerald", "olive")
COMMON_COMPANY_WORDS = {
    "CLASS",
    "COMMON",
    "CORP",
    "CORPORATION",
    "ETF",
    "FUND",
    "HOLDINGS",
    "INC",
    "INCORPORATED",
    "LTD",
    "NEW",
    "SHARES",
}


def build_live_underlying_stats(
    *,
    live_book: LivePositionBook,
    positions: Sequence[PositionSummary],
    executions: Sequence[Mapping[str, object]],
    cash_movements: Sequence[Mapping[str, object]],
    lifecycle_events: Sequence[Mapping[str, object]],
    daily_bars: Sequence[Mapping[str, object]],
    option_market: Sequence[Mapping[str, object]] = (),
    as_of: date,
) -> tuple[UnderlyingCallStats, ...]:
    dividends = _attribute_dividends(cash_movements, live_book.underlyings)
    equity_positions = {
        position.symbol: position
        for position in positions
        if position.asset_type.upper() != "OPTION" and position.quantity > ZERO
    }
    return tuple(
        _underlying_stats(
            item,
            holding=equity_positions.get(item.symbol),
            executions=executions,
            dividends=dividends.get(item.symbol, ()),
            lifecycle_events=lifecycle_events,
            daily_bars=daily_bars,
            option_market=option_market,
            as_of=as_of,
            tone=TONE_CYCLE[index % len(TONE_CYCLE)],
        )
        for index, item in enumerate(live_book.underlyings)
    )


def _underlying_stats(
    item: LiveUnderlyingPosition,
    *,
    holding: PositionSummary | None,
    executions: Sequence[Mapping[str, object]],
    dividends: Sequence[Mapping[str, object]],
    lifecycle_events: Sequence[Mapping[str, object]],
    daily_bars: Sequence[Mapping[str, object]],
    option_market: Sequence[Mapping[str, object]],
    as_of: date,
    tone: str,
) -> UnderlyingCallStats:
    symbol = item.symbol
    call_executions = tuple(
        row
        for row in executions
        if str(row.get("asset_type")) == "option"
        and str(row.get("option_side")) == "call"
        and str(row.get("underlying_symbol")) == symbol
    )
    symbol_lifecycle = tuple(
        row
        for row in lifecycle_events
        if str(row.get("option_side")) == "call" and str(row.get("underlying_symbol")) == symbol
    )
    price_points = _ensure_price_points(
        build_price_points(symbol, daily_bars),
        current_price=item.current_price or _first_underlying_price(item),
        as_of=as_of,
    )
    clocks = build_open_call_clocks(
        symbol,
        item.calls,
        executions=call_executions,
        daily_bars=daily_bars,
        option_market=option_market,
        as_of=as_of,
    )
    current_price = item.current_price or _first_underlying_price(item) or price_points[-1].price
    market_value = item.market_value or current_price * Decimal(item.shares)
    average_cost = item.average_price or current_price
    windows = _performance_windows(
        call_executions,
        dividends,
        capital=abs(market_value),
        as_of=as_of,
    )
    quarter_start = as_of - timedelta(days=90)
    quarter_executions = [
        row for row in call_executions if quarter_start <= _row_date(row) <= as_of
    ]
    quarter_lifecycle = [
        row for row in symbol_lifecycle if quarter_start <= _row_date(row) <= as_of
    ]
    openings = [row for row in call_executions if _is_opening_sale(row)]
    quarter_openings = [row for row in quarter_executions if _is_opening_sale(row)]
    quarter_closings = [row for row in quarter_executions if _is_closing_buy(row)]
    gross = sum((_gross_opening(row) for row in call_executions), ZERO)
    buyback = sum((_closing_debit(row) for row in call_executions), ZERO)
    net_option_cash = sum((_decimal(row.get("net_cash")) for row in call_executions), ZERO)
    dividend_cash = sum((_decimal(row.get("amount")) for row in dividends), ZERO)
    assigned_contracts = _lifecycle_contracts(quarter_lifecycle, "assignment")
    expired_contracts = _lifecycle_contracts(quarter_lifecycle, "expiration")
    open_credit = sum((clock.entry_credit for clock in clocks), ZERO)
    low = min(point.price for point in price_points)
    high = max(point.price for point in price_points)
    midpoint = (low + high) / Decimal("2")
    first_price = price_points[0].price
    current_range = current_price - low
    range_width = high - low
    current_symbols = {call.option_symbol for call in item.calls}
    current_marks = {
        call.option_symbol: call.estimated_mark_per_share
        for call in item.calls
        if call.estimated_mark_per_share is not None
    }
    basis_total = average_cost * Decimal(item.shares)
    total_attributed_income = net_option_cash + dividend_cash
    return UnderlyingCallStats(
        symbol=symbol,
        company_name=item.description,
        shares=item.shares,
        average_cost=average_cost,
        current_price=current_price,
        market_value=market_value,
        unrealized_profit_loss=(
            market_value - basis_total if item.shares and basis_total else ZERO
        ),
        contract_capacity=item.contract_capacity,
        active_contracts=item.open_call_contracts,
        coverage_percent=item.coverage_percent,
        call_tickets=len(quarter_openings),
        contracts_sold=sum((int(_decimal(row.get("quantity"))) for row in quarter_openings), 0),
        expired_contracts=expired_contracts,
        closed_contracts=sum((int(_decimal(row.get("quantity"))) for row in quarter_closings), 0),
        rolled_contracts=_rolled_contracts(quarter_executions),
        assigned_contracts=assigned_contracts,
        called_away_shares=assigned_contracts * 100,
        gross_premium=gross,
        buyback_cost=buyback,
        net_option_cash=net_option_cash,
        realized_option_income=net_option_cash,
        open_call_credit=open_credit,
        quarter_dividends=windows[1].dividends,
        quarter_total_cash=windows[1].total_cash,
        quarter_option_apr=windows[1].option_apr,
        quarter_total_cash_apr=windows[1].total_cash_apr,
        average_open_call_iv_percent=_weighted_average(
            (clock.implied_volatility_percent, clock.contracts)
            for clock in clocks
            if clock.implied_volatility_percent is not None
        ),
        average_open_call_delta=_weighted_average(
            (abs(clock.delta), clock.contracts) for clock in clocks if clock.delta is not None
        ),
        current_strike_buffer_percent=min(
            (clock.strike_distance_percent for clock in clocks),
            default=ZERO,
        ),
        next_ex_dividend_date=None,
        dividend_per_share=ZERO,
        dividend_overlap_contracts=0,
        premium_capture_percent=((gross - buyback) / gross * HUNDRED if gross else ZERO),
        lifetime_option_income=net_option_cash,
        lifetime_dividends=dividend_cash,
        income_adjusted_basis=basis_total - total_attributed_income,
        income_adjusted_basis_per_share=(
            (basis_total - total_attributed_income) / Decimal(item.shares) if item.shares else ZERO
        ),
        basis_offset_percent=(
            total_attributed_income / basis_total * HUNDRED if basis_total else ZERO
        ),
        average_strike_upside_percent=_average_entry_strike_buffer(
            openings,
            symbol=symbol,
            daily_bars=daily_bars,
        ),
        average_days_to_expiration=_average_entry_dte(openings),
        win_rate=ZERO,
        performance_windows=windows,
        open_call_clocks=clocks,
        thirteen_week_low=low,
        thirteen_week_mid=midpoint,
        thirteen_week_high=high,
        thirteen_week_change_percent=(
            (current_price / first_price - Decimal("1")) * HUNDRED if first_price else ZERO
        ),
        range_position_percent=(current_range / range_width * HUNDRED if range_width else ZERO),
        distance_from_high_percent=(
            (current_price / high - Decimal("1")) * HUNDRED if high else ZERO
        ),
        price_points=price_points,
        price_events=build_option_events(
            symbol,
            executions=call_executions,
            lifecycle_events=symbol_lifecycle,
            points=price_points,
            current_option_symbols=current_symbols,
            current_option_marks=current_marks,
        ),
        share_trade_events=build_share_trade_events(
            symbol,
            executions=executions,
            points=price_points,
        ),
        tone=tone,
    )


def _performance_windows(
    executions: Sequence[Mapping[str, object]],
    dividends: Sequence[Mapping[str, object]],
    *,
    capital: Decimal,
    as_of: date,
) -> tuple[UnderlyingPerformanceWindow, ...]:
    definitions = (
        ("month", as_of - timedelta(days=27)),
        ("quarter", as_of - timedelta(days=90)),
        ("ytd", date(as_of.year, 1, 1)),
        ("r365", as_of - timedelta(days=364)),
    )
    windows: list[UnderlyingPerformanceWindow] = []
    for key, start in definitions:
        rows = [row for row in executions if start <= _row_date(row) <= as_of]
        cash_rows = [row for row in dividends if start <= _row_date(row) <= as_of]
        gross = sum((_gross_opening(row) for row in rows), ZERO)
        buyback = sum((_closing_debit(row) for row in rows), ZERO)
        option_cash = sum((_decimal(row.get("net_cash")) for row in rows), ZERO)
        dividend_cash = sum((_decimal(row.get("amount")) for row in cash_rows), ZERO)
        days = Decimal((as_of - start).days + 1)
        annual_factor = YEAR_DAYS / days
        windows.append(
            UnderlyingPerformanceWindow(
                key=key,
                option_cash=option_cash,
                dividends=dividend_cash,
                total_cash=option_cash + dividend_cash,
                gross_premium=gross,
                buyback_cost=buyback,
                option_apr=(option_cash / capital * annual_factor * HUNDRED if capital else ZERO),
                total_cash_apr=(
                    (option_cash + dividend_cash) / capital * annual_factor * HUNDRED
                    if capital
                    else ZERO
                ),
                premium_capture_percent=((gross - buyback) / gross * HUNDRED if gross else ZERO),
            )
        )
    return tuple(windows)


def _attribute_dividends(
    cash_movements: Sequence[Mapping[str, object]],
    underlyings: Sequence[LiveUnderlyingPosition],
) -> dict[str, tuple[Mapping[str, object], ...]]:
    descriptions = {item.symbol: _distinctive_words(item.description) for item in underlyings}
    result: defaultdict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in cash_movements:
        if str(row.get("movement_type")) != "dividend":
            continue
        direct = str(row.get("symbol") or row.get("underlying_symbol") or "")
        if direct in descriptions:
            result[direct].append(row)
            continue
        words = _distinctive_words(str(row.get("description") or ""))
        candidates = [
            symbol for symbol, company_words in descriptions.items() if words & company_words
        ]
        if len(candidates) == 1:
            result[candidates[0]].append(row)
    return {symbol: tuple(rows) for symbol, rows in result.items()}


def _distinctive_words(value: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[A-Z0-9]+", value.upper())
        if len(word) >= 4 and word not in COMMON_COMPANY_WORDS
    }


def _ensure_price_points(
    points: Sequence[PricePoint],
    *,
    current_price: Decimal | None,
    as_of: date,
) -> tuple[PricePoint, ...]:
    if points:
        return tuple(points)
    price = current_price or ZERO
    return (
        PricePoint(
            date=as_of,
            label=as_of.strftime("%b %d"),
            price=price,
            x_percent=ZERO,
            y_percent=Decimal("50"),
            is_friday=as_of.weekday() == 4,
        ),
    )


def _first_underlying_price(item: LiveUnderlyingPosition) -> Decimal | None:
    options = (*item.calls, *item.puts)
    return options[0].underlying_price if options else None


def _weighted_average(values: Iterable[tuple[Decimal, int]]) -> Decimal:
    rows = tuple(values)
    weight = sum((contracts for _, contracts in rows), 0)
    return (
        sum((value * Decimal(contracts) for value, contracts in rows), ZERO) / Decimal(weight)
        if weight
        else ZERO
    )


def _average_entry_dte(rows: Sequence[Mapping[str, object]]) -> Decimal:
    values = [
        Decimal(max(0, (_date(row.get("expiration_date")) - _row_date(row)).days))
        for row in rows
        if row.get("expiration_date") is not None
    ]
    return sum(values, ZERO) / Decimal(len(values)) if values else ZERO


def _average_entry_strike_buffer(
    rows: Sequence[Mapping[str, object]],
    *,
    symbol: str,
    daily_bars: Sequence[Mapping[str, object]],
) -> Decimal:
    values: list[Decimal] = []
    for row in rows:
        close = _close_on_or_before(symbol, _row_date(row), daily_bars)
        strike = _decimal(row.get("strike"))
        if close:
            values.append((strike / close - Decimal("1")) * HUNDRED)
    return sum(values, ZERO) / Decimal(len(values)) if values else ZERO


def _close_on_or_before(
    symbol: str,
    value: date,
    daily_bars: Sequence[Mapping[str, object]],
) -> Decimal | None:
    rows = [
        row
        for row in daily_bars
        if str(row.get("symbol")) == symbol and _date(row.get("trade_date")) <= value
    ]
    if not rows:
        return None
    latest = max(rows, key=lambda row: _date(row.get("trade_date")))
    return _decimal(latest.get("close"))


def _rolled_contracts(rows: Sequence[Mapping[str, object]]) -> int:
    orders: defaultdict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        key = str(row.get("order_external_key") or "")
        if key:
            orders[key].append(row)
    total = 0
    for order_rows in orders.values():
        has_close = any(_is_closing_buy(row) for row in order_rows)
        if has_close:
            total += sum(
                int(_decimal(row.get("quantity"))) for row in order_rows if _is_opening_sale(row)
            )
    return total


def _lifecycle_contracts(rows: Sequence[Mapping[str, object]], event_type: str) -> int:
    return sum(
        int(_decimal(row.get("option_quantity")))
        for row in rows
        if str(row.get("event_type")) == event_type
    )


def _gross_opening(row: Mapping[str, object]) -> Decimal:
    return _decimal(row.get("gross_amount")) if _is_opening_sale(row) else ZERO


def _closing_debit(row: Mapping[str, object]) -> Decimal:
    return _decimal(row.get("gross_amount")) if _is_closing_buy(row) else ZERO


def _is_opening_sale(row: Mapping[str, object]) -> bool:
    return str(row.get("side")) == "sell" and str(row.get("position_effect")) == "opening"


def _is_closing_buy(row: Mapping[str, object]) -> bool:
    return str(row.get("side")) == "buy" and str(row.get("position_effect")) == "closing"


def _row_date(row: Mapping[str, object]) -> date:
    return _date(row.get("occurred_at"))


def _date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _decimal(value: object) -> Decimal:
    return ZERO if value is None else Decimal(str(value))
