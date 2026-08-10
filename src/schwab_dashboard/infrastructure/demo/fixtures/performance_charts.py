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

D = Decimal


def build_cash_chart_series(
    records: Sequence[CallSaleRecord],
    monthly: Sequence[MonthlyPerformanceSummary],
    as_of: date,
) -> tuple[CashChartSeries, ...]:
    call_events = build_call_cash_events(records)
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
    raw: list[tuple[str, Decimal, Decimal]] = []
    cursor = start
    while cursor <= end:
        bucket_end = min(end, cursor + timedelta(days=bucket_days - 1))
        raw.append(
            (
                f"{bucket_end:%b %d}",
                cash_total(call_events, start=cursor, end=bucket_end),
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
    rows = [(item.label, item.option_cash, item.dividends) for item in monthly]
    return CashChartSeries(key=key, label=label, grain="MONTHLY CASH", points=_chart_points(rows))


def _rolling_cash_series(
    monthly: Sequence[MonthlyPerformanceSummary],
) -> CashChartSeries:
    prior = (
        ("SEP", D("3395"), D("0")),
        ("OCT", D("2600"), D("0")),
        ("NOV", D("2100"), D("0")),
        ("DEC", D("1700"), D("1590")),
    )
    current = [(item.label, item.option_cash, item.dividends) for item in monthly]
    return CashChartSeries(
        key="r365",
        label="ROLLING 365",
        grain="MONTHLY CASH",
        points=_chart_points([*prior, *current]),
    )


def _chart_points(
    rows: Sequence[tuple[str, Decimal, Decimal]],
) -> tuple[CashChartPoint, ...]:
    maximum = max((abs(option + dividend) for _, option, dividend in rows), default=D("1"))
    return tuple(
        CashChartPoint(
            label=label.upper(),
            option_cash=option,
            dividends=dividend,
            total_cash=option + dividend,
            bar_percent=max(4, int(abs(option + dividend) / maximum * 100))
            if option + dividend
            else 0,
        )
        for label, option, dividend in rows
    )
