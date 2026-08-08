from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise

from schwab_dashboard.application.dashboard.covered_calls import (
    CallSaleRecord,
    PriceEvent,
    PricePoint,
)

D = Decimal
CENT = D("0.01")
TENTH = D("0.1")
HUNDRED = D("100")
WIGGLE = (D("-0.55"), D("0.35"), D("-0.20"), D("0.50"))


def build_daily_price_points(
    weekly_closes: Sequence[tuple[str, str]],
    year: int = 2026,
) -> tuple[PricePoint, ...]:
    anchors = tuple((_parse_label(label, year), D(price)) for label, price in weekly_closes)
    daily_prices: list[tuple[date, Decimal]] = [anchors[0]]
    for start, end in pairwise(anchors):
        daily_prices.extend(_interpolate_business_days(start, end))

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
    actions: list[tuple[date, str, str, str]] = []
    for record in records:
        if start <= record.sold_on <= end:
            actions.append(
                (
                    record.sold_on,
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
                    event_type,
                    glyph,
                    f"{verb} {record.contracts}x ${record.strike:g}C",
                )
            )

    lanes: dict[date, int] = {}
    events: list[PriceEvent] = []
    for event_date, event_type, glyph, detail in sorted(actions, key=lambda row: row[0]):
        point = min(points, key=lambda item: abs((item.date - event_date).days))
        lane = lanes.get(event_date, 0)
        lanes[event_date] = lane + 1
        events.append(
            PriceEvent(
                date=event_date,
                label=event_date.strftime("%m/%d"),
                event_type=event_type,
                glyph=glyph,
                detail=detail,
                x_percent=point.x_percent,
                y_percent=point.y_percent,
                vertical_offset=lane * 14,
            )
        )
    return tuple(events)


def _interpolate_business_days(
    start: tuple[date, Decimal],
    end: tuple[date, Decimal],
) -> tuple[tuple[date, Decimal], ...]:
    start_date, start_price = start
    end_date, end_price = end
    dates: list[date] = []
    cursor = start_date + timedelta(days=1)
    while cursor <= end_date:
        if cursor.weekday() < 5:
            dates.append(cursor)
        cursor += timedelta(days=1)

    delta = end_price - start_price
    amplitude = max(abs(delta) * D("0.08"), start_price * D("0.0015"))
    result: list[tuple[date, Decimal]] = []
    for index, point_date in enumerate(dates, start=1):
        fraction = D(index) / D(len(dates))
        price = start_price + delta * fraction
        if point_date != end_date:
            price += amplitude * WIGGLE[(index - 1) % len(WIGGLE)]
        result.append((point_date, price.quantize(CENT)))
    return tuple(result)


def _parse_label(label: str, year: int) -> date:
    month, day = (int(part) for part in label.split("/"))
    return date(year, month, day)
