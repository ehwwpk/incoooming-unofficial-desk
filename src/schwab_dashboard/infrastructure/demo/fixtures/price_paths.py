from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class _PriceAction:
    event_date: date
    lifecycle_id: int
    event_type: str
    glyph: str
    detail: str
    record: CallSaleRecord


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
    actions: list[_PriceAction] = []
    for lifecycle_id, record in enumerate(records, start=1):
        if start <= record.sold_on <= end:
            actions.append(
                _PriceAction(
                    event_date=record.sold_on,
                    lifecycle_id=lifecycle_id,
                    event_type="sale",
                    glyph="S",
                    detail=(
                        f"Sold {record.contracts}x ${record.strike:g}C / "
                        f"{record.days_to_expiration} DTE"
                    ),
                    record=record,
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
                _PriceAction(
                    event_date=record.closed_on,
                    lifecycle_id=lifecycle_id,
                    event_type=event_type,
                    glyph=glyph,
                    detail=f"{verb} {record.contracts}x ${record.strike:g}C",
                    record=record,
                )
            )

    ordered_actions = sorted(actions, key=lambda action: action.event_date)
    sale_sequences = {
        action.lifecycle_id: sequence
        for sequence, action in enumerate(ordered_actions, start=1)
        if action.event_type == "sale"
    }
    resolution_sequences = {
        action.lifecycle_id: sequence
        for sequence, action in enumerate(ordered_actions, start=1)
        if action.event_type != "sale"
    }
    resolution_prices = {
        action.lifecycle_id: min(
            points,
            key=lambda item: abs((item.date - action.event_date).days),
        ).price
        for action in ordered_actions
        if action.event_type != "sale"
    }
    lanes: dict[date, int] = {}
    events: list[PriceEvent] = []
    for sequence, action in enumerate(ordered_actions, start=1):
        point = min(points, key=lambda item: abs((item.date - action.event_date).days))
        lane = lanes.get(action.event_date, 0)
        lanes[action.event_date] = lane + 1
        option_value_per_share = _checkpoint_option_value(action.record)
        events.append(
            PriceEvent(
                sequence=sequence,
                lifecycle_id=action.lifecycle_id,
                record_id=action.record.record_id,
                campaign_id=action.record.campaign_id,
                date=action.event_date,
                label=action.event_date.strftime("%m/%d"),
                event_type=action.event_type,
                glyph=action.glyph,
                detail=action.detail,
                price=point.price,
                x_percent=point.x_percent,
                y_percent=point.y_percent,
                vertical_offset=lane * 14,
                linked_sale_sequence=(
                    None if action.event_type == "sale" else sale_sequences.get(action.lifecycle_id)
                ),
                linked_resolution_sequence=(
                    resolution_sequences.get(action.lifecycle_id)
                    if action.event_type == "sale"
                    else None
                ),
                resolved_on=(
                    action.record.closed_on if action.lifecycle_id in resolution_prices else None
                ),
                underlying_at_resolution=resolution_prices.get(action.lifecycle_id),
                expires_on=action.record.expires_on,
                contracts=action.record.contracts,
                strike=action.record.strike,
                underlying_at_sale=action.record.underlying_at_sale,
                strike_upside_percent=action.record.strike_upside_percent,
                entry_days_to_expiration=action.record.days_to_expiration,
                premium_per_share=action.record.premium_per_share,
                gross_premium=action.record.gross_premium,
                buyback_cost=action.record.buyback_cost,
                net_cash=action.record.net_cash,
                outcome=action.record.outcome,
                option_value_per_share=option_value_per_share,
                option_value_vs_credit_percent=(
                    option_value_per_share / action.record.premium_per_share * D("100")
                    if option_value_per_share is not None
                    and action.record.premium_per_share
                    else None
                ),
            )
        )
    return tuple(events)


def _checkpoint_option_value(record: CallSaleRecord) -> Decimal | None:
    outcome = record.outcome.lower()
    if outcome == "expired":
        return D("0")
    if outcome in {"closed", "rolled"} and record.contracts:
        return record.buyback_cost / D(str(record.contracts * 100))
    return None


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
