from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal

from schwab_dashboard.application.dashboard.cashflows import (
    CashEvent,
    build_call_cash_events,
    cash_total,
)
from schwab_dashboard.application.dashboard.covered_calls import CallSaleRecord
from schwab_dashboard.application.dashboard.performance import (
    MonthlyPerformanceSummary,
    PerformanceWindowSummary,
)
from schwab_dashboard.infrastructure.demo.fixtures.cash_events import (
    build_dividend_cash_events,
)

D = Decimal
ZERO = D("0")
MONEY = D("0.01")
TENTH = D("0.1")
YEAR_DAYS = D("365")
MONTH_DAYS = YEAR_DAYS / D("12")
MONTHLY_TARGET = D("3000")


def build_performance_windows(
    records: Sequence[CallSaleRecord],
    stock_value: Decimal,
    as_of: date,
    monthly: Sequence[MonthlyPerformanceSummary],
) -> tuple[PerformanceWindowSummary, ...]:
    call_events = build_call_cash_events(records)
    dividend_events = build_dividend_cash_events()
    month_start = as_of - timedelta(days=27)
    quarter_start = min(record.sold_on for record in records)
    ytd_option = sum((item.option_cash for item in monthly), ZERO)
    ytd_dividends = sum((item.dividends for item in monthly), ZERO)
    ytd_gross = sum((item.gross_premium for item in monthly), ZERO)
    ytd_debits = sum((item.closing_debits + item.fees for item in monthly), ZERO)
    return (
        _execution_window(
            "month",
            "4 WEEKS",
            month_start,
            as_of,
            call_events,
            dividend_events,
            records,
            stock_value,
        ),
        _execution_window(
            "quarter",
            "QUARTERLY",
            quarter_start,
            as_of,
            call_events,
            dividend_events,
            records,
            stock_value,
        ),
        _window(
            key="ytd",
            label="CALENDAR YTD",
            range_label=f"Jan 01 - {as_of:%b %d}",
            days=(as_of - date(as_of.year, 1, 1)).days + 1,
            option_cash=ytd_option,
            dividends=ytd_dividends,
            gross_premium=ytd_gross,
            buyback_cost=ytd_debits,
            tickets=31,
            contracts=108,
            completed=25,
            wins=21,
            stock_value=stock_value,
        ),
        _window(
            key="r365",
            label="ROLLING 365",
            range_label=(f"{as_of - timedelta(days=364):%b %d, %Y} - {as_of:%b %d, %Y}"),
            days=365,
            option_cash=ytd_option + D("9795"),
            dividends=ytd_dividends + D("1590"),
            gross_premium=ytd_gross + D("14100"),
            buyback_cost=ytd_debits + D("4305"),
            tickets=58,
            contracts=202,
            completed=48,
            wins=41,
            stock_value=stock_value,
        ),
    )


def _execution_window(
    key: str,
    label: str,
    start: date,
    end: date,
    call_events: Sequence[CashEvent],
    dividend_events: Sequence[CashEvent],
    records: Sequence[CallSaleRecord],
    stock_value: Decimal,
) -> PerformanceWindowSummary:
    gross = cash_total(call_events, start=start, end=end, event_types=frozenset({"OPENING CREDIT"}))
    debit_cash = cash_total(
        call_events,
        start=start,
        end=end,
        event_types=frozenset({"CLOSING DEBIT", "FEES"}),
    )
    opened = [record for record in records if start <= record.sold_on <= end]
    completed = [
        record
        for record in records
        if record.closed_on is not None
        and start <= record.closed_on <= end
        and record.outcome != "Open"
    ]
    return _window(
        key=key,
        label=label,
        range_label=f"{start:%b %d} - {end:%b %d}",
        days=(end - start).days + 1,
        option_cash=cash_total(call_events, start=start, end=end),
        dividends=cash_total(dividend_events, start=start, end=end),
        gross_premium=gross,
        buyback_cost=-debit_cash,
        tickets=len(opened),
        contracts=sum(record.contracts for record in opened),
        completed=len(completed),
        wins=sum(1 for record in completed if record.net_cash - record.fees > ZERO),
        stock_value=stock_value,
    )


def _window(
    *,
    key: str,
    label: str,
    range_label: str,
    days: int,
    option_cash: Decimal,
    dividends: Decimal,
    gross_premium: Decimal,
    buyback_cost: Decimal,
    tickets: int,
    contracts: int,
    completed: int,
    wins: int,
    stock_value: Decimal,
) -> PerformanceWindowSummary:
    annual_factor = YEAR_DAYS / D(days)
    monthly_run_rate = (option_cash * MONTH_DAYS / D(days)).quantize(MONEY)
    total_cash = option_cash + dividends
    monthly_total_run_rate = (total_cash * MONTH_DAYS / D(days)).quantize(MONEY)
    return PerformanceWindowSummary(
        key=key,
        label=label,
        range_label=range_label,
        days=days,
        option_cash=option_cash,
        dividends=dividends,
        total_cash=total_cash,
        gross_premium=gross_premium,
        buyback_cost=buyback_cost,
        call_tickets=tickets,
        contracts=contracts,
        completed_trades=completed,
        win_rate=(D(wins) / D(completed) * 100).quantize(TENTH) if completed else ZERO,
        annualized_option_yield=(option_cash / stock_value * annual_factor * 100).quantize(TENTH),
        annualized_total_yield=(total_cash / stock_value * annual_factor * 100).quantize(TENTH),
        monthly_option_run_rate=monthly_run_rate,
        monthly_total_run_rate=monthly_total_run_rate,
        target_cash_for_window=(MONTHLY_TARGET * D(days) / MONTH_DAYS).quantize(MONEY),
        target_progress_percent=max(ZERO, monthly_run_rate / MONTHLY_TARGET * 100).quantize(TENTH),
        premium_capture_percent=(option_cash / gross_premium * 100).quantize(TENTH)
        if gross_premium
        else ZERO,
        buyback_drag_percent=(buyback_cost / gross_premium * 100).quantize(TENTH)
        if gross_premium
        else ZERO,
    )
