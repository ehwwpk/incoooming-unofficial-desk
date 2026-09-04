from __future__ import annotations

from calendar import month_abbr
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal

from schwab_dashboard.application.dashboard.performance import (
    CashChartPoint,
    CashChartSeries,
)
from schwab_dashboard.application.dashboard.short_premium import (
    is_closing_buy as _is_closing_buy,
)
from schwab_dashboard.application.dashboard.short_premium import (
    is_opening_sale as _is_opening_sale,
)
from schwab_dashboard.application.market_time import ledger_market_date

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def build_live_cash_chart_series(
    *,
    executions: Sequence[Mapping[str, object]],
    dividends: Sequence[Mapping[str, object]],
    as_of: date,
) -> tuple[CashChartSeries, ...]:
    """Build display series only from normalized, dated cash records."""

    if not executions and not dividends:
        return ()

    month_start = as_of - timedelta(days=27)
    quarter_start = as_of - timedelta(days=90)
    r365_start = as_of - timedelta(days=364)
    return (
        _series(
            key="month",
            label="4W DAILY CASH",
            grain="DAILY CASH",
            buckets=_daily_buckets(month_start, as_of),
            executions=executions,
            dividends=dividends,
        ),
        _series(
            key="quarter",
            label="QTR WEEKLY CASH",
            grain="WEEKLY CASH",
            buckets=_weekly_buckets(quarter_start, as_of),
            executions=executions,
            dividends=dividends,
        ),
        _series(
            key="ytd",
            label="YTD MONTHLY CASH",
            grain="MONTHLY CASH",
            buckets=_monthly_buckets(date(as_of.year, 1, 1), as_of),
            executions=executions,
            dividends=dividends,
        ),
        _series(
            key="r365",
            label="R365 MONTHLY CASH",
            grain="MONTHLY CASH",
            buckets=_monthly_buckets(r365_start, as_of),
            executions=executions,
            dividends=dividends,
        ),
    )


def _series(
    *,
    key: str,
    label: str,
    grain: str,
    buckets: Sequence[tuple[str, date, date]],
    executions: Sequence[Mapping[str, object]],
    dividends: Sequence[Mapping[str, object]],
) -> CashChartSeries:
    raw: list[tuple[str, Decimal, Decimal, Decimal, Decimal]] = []
    for bucket_label, start, end in buckets:
        trades = [row for row in executions if start <= _row_date(row) <= end]
        distributions = [row for row in dividends if start <= _row_date(row) <= end]
        raw.append(
            (
                bucket_label,
                sum((_opening_credit(row) for row in trades), ZERO),
                sum((_closing_debit(row) for row in trades), ZERO),
                sum((_decimal(row.get("net_cash")) for row in trades), ZERO),
                sum((_decimal(row.get("amount")) for row in distributions), ZERO),
            )
        )

    max_credit = max((item[1] for item in raw), default=ZERO)
    max_debit = max((item[2] for item in raw), default=ZERO)
    max_total = max((abs(item[3] + item[4]) for item in raw), default=ZERO)
    points = tuple(
        CashChartPoint(
            label=bucket_label,
            premium_received=premium,
            executed_debits=debits,
            option_cash=option_cash,
            dividends=dividend_cash,
            total_cash=option_cash + dividend_cash,
            bar_percent=_percent(abs(option_cash + dividend_cash), max_total),
            credit_bar_percent=_percent(premium, max_credit),
            debit_bar_percent=_percent(debits, max_debit),
        )
        for bucket_label, premium, debits, option_cash, dividend_cash in raw
    )
    return CashChartSeries(key=key, label=label, grain=grain, points=points)


def _daily_buckets(start: date, end: date) -> tuple[tuple[str, date, date], ...]:
    return tuple(
        ((start + timedelta(days=offset)).strftime("%b %d").upper(), day, day)
        for offset in range((end - start).days + 1)
        for day in (start + timedelta(days=offset),)
    )


def _weekly_buckets(start: date, end: date) -> tuple[tuple[str, date, date], ...]:
    result: list[tuple[str, date, date]] = []
    cursor = start
    while cursor <= end:
        bucket_end = min(end, cursor + timedelta(days=6))
        result.append((f"{cursor.month}/{cursor.day}", cursor, bucket_end))
        cursor = bucket_end + timedelta(days=1)
    return tuple(result)


def _monthly_buckets(start: date, end: date) -> tuple[tuple[str, date, date], ...]:
    result: list[tuple[str, date, date]] = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        next_month = _next_month(cursor)
        bucket_start = max(start, cursor)
        bucket_end = min(end, next_month - timedelta(days=1))
        label = month_abbr[cursor.month].upper()
        if cursor.year != end.year:
            label = f"{label} {str(cursor.year)[2:]}"
        result.append((label, bucket_start, bucket_end))
        cursor = next_month
    return tuple(result)


def _next_month(value: date) -> date:
    return date(value.year + (value.month == 12), value.month % 12 + 1, 1)


def _opening_credit(row: Mapping[str, object]) -> Decimal:
    return _decimal(row.get("gross_amount")) if _is_opening_sale(row) else ZERO


def _closing_debit(row: Mapping[str, object]) -> Decimal:
    return _decimal(row.get("gross_amount")) if _is_closing_buy(row) else ZERO


def _row_date(row: Mapping[str, object]) -> date:
    value = row.get("occurred_at")
    if isinstance(value, (date, datetime)):
        return ledger_market_date(value)
    raise ValueError("Ledger row is missing its source date")


def _decimal(value: object) -> Decimal:
    return ZERO if value is None else Decimal(str(value))


def _percent(value: Decimal, maximum: Decimal) -> int:
    return max(0, min(100, int(value / maximum * HUNDRED))) if maximum else 0
