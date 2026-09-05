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
    CashChartPoint,
    CashChartSeries,
    MonthlyPerformanceSummary,
)
from schwab_dashboard.infrastructure.demo.fixtures.cash_events import (
    build_dividend_cash_events,
)
from schwab_dashboard.infrastructure.demo.fixtures.short_puts import build_put_cash_events

D = Decimal


def build_cash_chart_series(
    records: Sequence[CallSaleRecord],
    monthly: Sequence[MonthlyPerformanceSummary],
    as_of: date,
) -> tuple[CashChartSeries, ...]:
    call_events = (*build_call_cash_events(records), *build_put_cash_events())
    dividend_events = build_dividend_cash_events()
    return (
        _dated_cash_series(
            "month",
            "4 WEEKS",
            "DAILY CASH",
            as_of - timedelta(days=27),
            as_of,
            1,
            call_events,
            dividend_events,
        ),
        _dated_cash_series(
            "quarter",
            "QUARTERLY",
            "WEEKLY CASH",
            min(record.sold_on for record in records),
            as_of,
            7,
            call_events,
            dividend_events,
        ),
        _monthly_cash_series("ytd", "CALENDAR YTD", monthly),
        _rolling_cash_series(monthly),
    )


def _dated_cash_series(
    key: str,
    label: str,
    grain: str,
    start: date,
    end: date,
    bucket_days: int,
    call_events: Sequence[CashEvent],
    dividend_events: Sequence[CashEvent],
) -> CashChartSeries:
    raw: list[tuple[str, Decimal, Decimal, Decimal]] = []
    cursor = start
    while cursor <= end:
        bucket_end = min(end, cursor + timedelta(days=bucket_days - 1))
        premium_received = cash_total(
            call_events,
            start=cursor,
            end=bucket_end,
            event_types=frozenset({"OPENING CREDIT"}),
        )
        executed_debits = -cash_total(
            call_events,
            start=cursor,
            end=bucket_end,
            event_types=frozenset({"CLOSING DEBIT", "FEES"}),
        )
        raw.append(
            (
                f"{bucket_end:%b %d}",
                premium_received,
                executed_debits,
                cash_total(dividend_events, start=cursor, end=bucket_end),
            )
        )
        cursor = bucket_end + timedelta(days=1)
    return CashChartSeries(key=key, label=label, grain=grain, points=_chart_points(raw))


def _monthly_cash_series(
    key: str,
    label: str,
    monthly: Sequence[MonthlyPerformanceSummary],
) -> CashChartSeries:
    rows = [
        (
            item.label,
            item.gross_premium,
            item.closing_debits + item.fees,
            item.dividends,
        )
        for item in monthly
    ]
    return CashChartSeries(key=key, label=label, grain="MONTHLY CASH", points=_chart_points(rows))


def _rolling_cash_series(
    monthly: Sequence[MonthlyPerformanceSummary],
) -> CashChartSeries:
    prior = (
        ("SEP", D("4400"), D("1005"), D("0")),
        ("OCT", D("3900"), D("1300"), D("0")),
        ("NOV", D("3100"), D("1000"), D("0")),
        ("DEC", D("2700"), D("1000"), D("1590")),
    )
    current = [
        (
            item.label,
            item.gross_premium,
            item.closing_debits + item.fees,
            item.dividends,
        )
        for item in monthly
    ]
    return CashChartSeries(
        key="r365",
        label="ROLLING 365",
        grain="MONTHLY CASH",
        points=_chart_points([*prior, *current]),
    )


def _chart_points(
    rows: Sequence[tuple[str, Decimal, Decimal, Decimal]],
) -> tuple[CashChartPoint, ...]:
    maximum = max(
        (
            max(premium, executed_debits, abs(premium - executed_debits + dividends))
            for _, premium, executed_debits, dividends in rows
        ),
        default=D("1"),
    )
    return tuple(
        CashChartPoint(
            label=label.upper(),
            premium_received=premium,
            executed_debits=executed_debits,
            option_cash=premium - executed_debits,
            dividends=dividend,
            total_cash=premium - executed_debits + dividend,
            bar_percent=max(
                4,
                int(abs(premium - executed_debits + dividend) / maximum * 100),
            )
            if premium - executed_debits + dividend
            else 0,
            credit_bar_percent=max(4, int(premium / maximum * 100)) if premium else 0,
            debit_bar_percent=max(4, int(executed_debits / maximum * 100))
            if executed_debits
            else 0,
        )
        for label, premium, executed_debits, dividend in rows
    )
