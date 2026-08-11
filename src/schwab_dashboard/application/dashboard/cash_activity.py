from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from schwab_dashboard.application.dashboard.cashflows import CashEvent
from schwab_dashboard.application.dashboard.covered_calls import CallSaleRecord
from schwab_dashboard.application.dashboard.performance import (
    CashActivityItem,
    CashActivityWindow,
    PerformanceWindowSummary,
)


def build_cash_activity_windows(
    cash_events: Sequence[CashActivityItem],
    performance_windows: Sequence[PerformanceWindowSummary],
    as_of: date,
    *,
    event_limit: int = 3,
) -> tuple[CashActivityWindow, ...]:
    """Build compact, execution-only Desk views from the reconciled cash ledger."""

    return tuple(
        _activity_window(
            window,
            cash_events,
            as_of,
            event_limit=event_limit,
        )
        for window in performance_windows
    )


def build_cash_activity_items(
    records: Sequence[CallSaleRecord],
    call_events: Sequence[CashEvent],
    dividend_events: Sequence[CashEvent],
) -> tuple[CashActivityItem, ...]:
    records_by_id = {record.record_id: record for record in records}
    return tuple(
        _activity_item(event, records_by_id)
        for event in sorted(
            (*call_events, *dividend_events),
            key=lambda event: (event.occurred_on, event.event_id),
            reverse=True,
        )
        if event.amount
    )


def _activity_window(
    window: PerformanceWindowSummary,
    events: Sequence[CashActivityItem],
    as_of: date,
    *,
    event_limit: int,
) -> CashActivityWindow:
    start = as_of - timedelta(days=window.days - 1)
    recent = [event for event in events if start <= event.occurred_on <= as_of][:event_limit]
    return CashActivityWindow(
        key=window.key,
        label=window.label,
        range_label=window.range_label,
        premium_received=window.gross_premium,
        executed_debits=window.buyback_cost,
        dividends=window.dividends,
        net_option_cash=window.option_cash,
        total_strategy_cash=window.total_cash,
        events=tuple(recent),
    )


def _activity_item(
    event: CashEvent,
    records_by_id: dict[str, CallSaleRecord],
) -> CashActivityItem:
    record_id = event.event_id.rsplit(":", maxsplit=1)[0]
    record = records_by_id.get(record_id)
    action_label = {
        "DIVIDEND": "DIVIDEND RECEIVED",
        "FEES": "FEES",
        "OPENING CREDIT": "CALL SOLD",
    }.get(event.event_type, "CALL CLOSED")
    if event.event_type == "CLOSING DEBIT" and record is not None and record.outcome == "Rolled":
        action_label = "CALL ROLLED"
    tone = "dividend" if event.event_type == "DIVIDEND" else (
        "credit" if event.amount > 0 else "debit"
    )
    return CashActivityItem(
        event_id=event.event_id,
        occurred_on=event.occurred_on,
        symbol=event.symbol,
        action_label=action_label,
        amount=event.amount,
        contracts=event.contracts,
        tone=tone,
        anchor_id=f"{event.symbol.lower()}-workspace",
    )
