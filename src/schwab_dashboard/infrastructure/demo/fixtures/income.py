from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal

from schwab_dashboard.application.dashboard.cashflows import (
    build_call_cash_events,
    cash_total,
)
from schwab_dashboard.application.dashboard.covered_calls import CallSaleRecord
from schwab_dashboard.application.dashboard.models import IncomePeriod
from schwab_dashboard.infrastructure.demo.fixtures.cash_events import (
    build_dividend_cash_events,
)

D = Decimal


def build_income_periods(
    records: Sequence[CallSaleRecord],
) -> tuple[IncomePeriod, ...]:
    """Legacy API projection derived from the same execution events as cash charts."""

    call_events = build_call_cash_events(records)
    dividend_events = build_dividend_cash_events()
    start = min(record.sold_on for record in records)
    end = max(event.occurred_on for event in (*call_events, *dividend_events))
    raw: list[tuple[str, Decimal, Decimal]] = []
    cursor = start
    while cursor <= end:
        bucket_end = min(end, cursor + timedelta(days=6))
        raw.append(
            (
                f"{bucket_end:%b %d}",
                cash_total(call_events, start=cursor, end=bucket_end),
                cash_total(dividend_events, start=cursor, end=bucket_end),
            )
        )
        cursor = bucket_end + timedelta(days=1)
    maximum = max(abs(option + dividends) for _, option, dividends in raw)
    return tuple(
        IncomePeriod(
            label=label,
            option_income=option,
            dividends=dividends,
            total=option + dividends,
            bar_percent=max(8, int(abs(option + dividends) / maximum * 100))
            if option + dividends
            else 0,
        )
        for label, option, dividends in raw
    )
