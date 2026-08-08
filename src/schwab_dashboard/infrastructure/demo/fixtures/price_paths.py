from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import (
    CallSaleRecord,
    PriceEvent,
    PricePoint,
    ShareTradeEvent,
)
from schwab_dashboard.infrastructure.demo.fixtures.share_trades import ShareTradeFixture

D = Decimal
TENTH = D("0.1")
HUNDRED = D("100")


def build_daily_price_points(
    daily_closes: Sequence[tuple[str, str]],
    year: int = 2026,
) -> tuple[PricePoint, ...]:
    daily_prices = tuple((_parse_label(label, year), D(price)) for label, price in daily_closes)
    if len(daily_prices) < 2:
        raise ValueError("Daily price history requires at least two observations")
    dates = tuple(point_date for point_date, _ in daily_prices)
    if dates != tuple(sorted(set(dates))):
        raise ValueError("Daily price history dates must be unique and chronological")

    prices = [price for _, price in daily_prices]
    low, high = min(prices), max(prices)
    spread = high - low
    last_index = len(daily_prices) - 1
    return tuple(
        PricePoint(
            date=point_date,
            label=point_date.strftime("%m/%d"),
            price=price,
            x_percent=(D(index) / D(last_index) * HUNDRED).quantize(TENTH),
            y_percent=(
                D("50.0")
                if not spread
                else (D("88") - (price - low) / spread * D("76")).quantize(TENTH)
            ),
            is_friday=point_date.weekday() == 4,
        )
        for index, (point_date, price) in enumerate(daily_prices)
    )


def build_price_events(
    records: Sequence[CallSaleRecord],
    points: Sequence[PricePoint],
    as_of: date,
) -> tuple[PriceEvent, ...]:
    if not points:
        return ()
    start, end = points[0].date, points[-1].date
    actions: list[tuple[date, int, str, str, str]] = []
    for lifecycle_id, record in enumerate(records, start=1):
        if start <= record.sold_on <= end:
            actions.append(
                (
                    record.sold_on,
                    lifecycle_id,
                    "sale",
                    "S",
                    (
                        f"Sold {record.contracts}x ${record.strike:g}C / "
                        f"{record.days_to_expiration} DTE"
                    ),
                )
            )
        if (
            record.outcome != "Open"
            and record.closed_on is not None
            and start <= record.closed_on <= min(end, as_of)
        ):
            event_type, glyph, verb = {
                "Expired": ("expired", "X", "Expired"),
                "Closed": ("closed", "C", "Closed"),
                "Rolled": ("rolled", "R", "Rolled"),
                "Assigned": ("assigned", "A", "Assigned"),
            }[record.outcome]
            actions.append(
                (
                    record.closed_on,
                    lifecycle_id,
                    event_type,
                    glyph,
                    f"{verb} {record.contracts}x ${record.strike:g}C",
                )
            )

    ordered_actions = sorted(actions, key=lambda row: row[0])
    sale_sequences = {
        lifecycle_id: sequence
        for sequence, (_, lifecycle_id, event_type, _, _) in enumerate(ordered_actions, start=1)
        if event_type == "sale"
    }
    lanes: dict[date, int] = {}
    events: list[PriceEvent] = []
    for sequence, (event_date, lifecycle_id, event_type, glyph, detail) in enumerate(
        ordered_actions, start=1
    ):
        point = min(points, key=lambda item: abs((item.date - event_date).days))
        lane = lanes.get(event_date, 0)
        lanes[event_date] = lane + 1
        events.append(
            PriceEvent(
                sequence=sequence,
                lifecycle_id=lifecycle_id,
                date=event_date,
                label=event_date.strftime("%m/%d"),
                event_type=event_type,
                glyph=glyph,
                detail=detail,
                price=point.price,
                x_percent=point.x_percent,
                y_percent=point.y_percent,
                vertical_offset=lane * 14,
                linked_sale_sequence=(
                    None if event_type == "sale" else sale_sequences.get(lifecycle_id)
                ),
            )
        )
    return tuple(events)


def build_share_trade_events(
    trades: Sequence[ShareTradeFixture],
    points: Sequence[PricePoint],
) -> tuple[ShareTradeEvent, ...]:
    """Project sparse share trades onto the same truthful daily-close anchors."""
    if not points:
        return ()
    start, end = points[0].date, points[-1].date
    events: list[ShareTradeEvent] = []
    for trade in sorted(trades, key=lambda item: item.traded_on):
        if not start <= trade.traded_on <= end:
            continue
        if trade.action not in {"buy", "sell"}:
            raise ValueError(f"Unsupported share trade action: {trade.action}")
        point = min(points, key=lambda item: abs((item.date - trade.traded_on).days))
        events.append(
            ShareTradeEvent(
                date=trade.traded_on,
                label=trade.traded_on.strftime("%m/%d"),
                action=trade.action,
                glyph="+" if trade.action == "buy" else "-",
                shares=trade.shares,
                price=trade.price,
                x_percent=point.x_percent,
                y_percent=point.y_percent,
            )
        )
    return tuple(events)


def _parse_label(label: str, year: int) -> date:
    month, day = (int(part) for part in label.split("/"))
    return date(year, month, day)
