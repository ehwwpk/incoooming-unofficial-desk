from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import (
    CallSaleRecord,
    UnderlyingCallStats,
)
from schwab_dashboard.application.dashboard.performance import (
    PerformanceWindowSummary,
    StrategyAttributionSummary,
)
from schwab_dashboard.application.values import sum_if_complete
from schwab_dashboard.infrastructure.demo.fixtures.daily_prices import DAILY_CLOSES

D = Decimal
ZERO = D("0")
TENTH = D("0.1")


def build_strategy_attribution(
    records: Sequence[CallSaleRecord],
    underlyings: Sequence[UnderlyingCallStats],
    windows: Sequence[PerformanceWindowSummary],
    as_of: date,
) -> tuple[StrategyAttributionSummary, ...]:
    by_key = {window.key: window for window in windows}
    return (
        _attribution_row(
            "month",
            "4 WEEKS",
            as_of - timedelta(days=27),
            records,
            underlyings,
            by_key["month"],
        ),
        _attribution_row(
            "quarter",
            "QUARTERLY",
            min(record.sold_on for record in records),
            records,
            underlyings,
            by_key["quarter"],
        ),
        _unavailable_attribution("ytd", "CALENDAR YTD", by_key["ytd"]),
        _unavailable_attribution("r365", "ROLLING 365", by_key["r365"]),
    )


def _attribution_row(
    key: str,
    label: str,
    start: date,
    records: Sequence[CallSaleRecord],
    underlyings: Sequence[UnderlyingCallStats],
    window: PerformanceWindowSummary,
) -> StrategyAttributionSummary:
    starting_prices = _prices_on_or_after(start)
    underlying_change = sum(
        ((item.current_price - starting_prices[item.symbol]) * item.shares for item in underlyings),
        ZERO,
    )
    open_mark = sum_if_complete(
        (
            clock.open_profit_loss
            for item in underlyings
            for clock in item.open_call_clocks
            if clock.sold_on is not None and clock.sold_on >= start
        ),
    )
    assert open_mark is not None
    completed_option_result = sum(
        (
            record.net_cash - record.fees
            for record in records
            if record.closed_on is not None
            and record.closed_on >= start
            and record.sold_on >= start
            and record.outcome != "Open"
        ),
        ZERO,
    )
    capped_upside = sum(
        (
            max(ZERO, item.current_price - record.strike) * record.contracts * 100
            for record in records
            for item in underlyings
            if item.symbol == record.symbol
            and record.outcome == "Assigned"
            and record.closed_on is not None
            and record.closed_on >= start
        ),
        ZERO,
    )
    capital = sum((item.current_price * item.shares for item in underlyings), ZERO)
    stock_only = underlying_change + window.dividends
    actual = stock_only + completed_option_result + open_mark
    return StrategyAttributionSummary(
        key=key,
        label=label,
        actual_result=actual,
        stock_only_result=stock_only,
        active_management_difference=actual - stock_only,
        underlying_change=underlying_change,
        dividends=window.dividends,
        completed_option_result=completed_option_result,
        open_option_mark=open_mark,
        capped_upside=capped_upside,
        average_capital=capital,
        actual_return_percent=(actual / capital * 100).quantize(TENTH),
        stock_only_return_percent=(stock_only / capital * 100).quantize(TENTH),
        status="CURRENT-INVENTORY PROXY",
        method_note=(
            "Uses current share counts, frozen closes, completed option results, and "
            "the simulated mark on calls opened inside this window."
        ),
    )


def _unavailable_attribution(
    key: str,
    label: str,
    window: PerformanceWindowSummary,
) -> StrategyAttributionSummary:
    note = (
        "Cash is complete for the demo ledger; a defensible stock-only comparison "
        "also needs daily share counts and historical option marks."
    )
    return StrategyAttributionSummary(
        key=key,
        label=label,
        actual_result=None,
        stock_only_result=None,
        active_management_difference=None,
        underlying_change=None,
        dividends=window.dividends,
        completed_option_result=window.option_cash,
        open_option_mark=None,
        capped_upside=None,
        average_capital=None,
        actual_return_percent=None,
        stock_only_return_percent=None,
        status="UNAVAILABLE UNTIL DAILY INVENTORY HISTORY",
        method_note=note,
    )


def _prices_on_or_after(start: date) -> dict[str, Decimal]:
    prices: dict[str, Decimal] = {}
    for symbol, rows in DAILY_CLOSES.items():
        dated = [(date(2026, int(label[:2]), int(label[3:])), D(value)) for label, value in rows]
        prices[symbol] = next(value for observed, value in dated if observed >= start)
    return prices
