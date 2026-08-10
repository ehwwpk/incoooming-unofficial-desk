from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import CallSaleRecord

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class CashEvent:
    event_id: str
    occurred_on: date
    symbol: str
    event_type: str
    amount: Decimal
    contracts: int


def build_call_cash_events(records: Sequence[CallSaleRecord]) -> tuple[CashEvent, ...]:
    """Convert lifecycle records into dated executions without mark-to-market estimates."""

    events: list[CashEvent] = []
    for record in records:
        events.append(
            CashEvent(
                event_id=f"{record.record_id}:open",
                occurred_on=record.sold_on,
                symbol=record.symbol,
                event_type="OPENING CREDIT",
                amount=record.gross_premium,
                contracts=record.contracts,
            )
        )
        if record.buyback_cost and record.closed_on is not None:
            events.append(
                CashEvent(
                    event_id=f"{record.record_id}:close",
                    occurred_on=record.closed_on,
                    symbol=record.symbol,
                    event_type="CLOSING DEBIT",
                    amount=-record.buyback_cost,
                    contracts=record.contracts,
                )
            )
        if record.fees:
            events.append(
                CashEvent(
                    event_id=f"{record.record_id}:fees",
                    occurred_on=record.sold_on,
                    symbol=record.symbol,
                    event_type="FEES",
                    amount=-record.fees,
                    contracts=record.contracts,
                )
            )
    return tuple(sorted(events, key=lambda item: (item.occurred_on, item.event_id)))


def cash_total(
    events: Iterable[CashEvent],
    *,
    start: date,
    end: date,
    event_types: frozenset[str] | None = None,
) -> Decimal:
    return sum(
        (
            event.amount
            for event in events
            if start <= event.occurred_on <= end
            and (event_types is None or event.event_type in event_types)
        ),
        ZERO,
    )
