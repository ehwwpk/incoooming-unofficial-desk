from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import (
    PriceEvent,
    PricePoint,
    ShareTradeEvent,
)
from schwab_dashboard.application.formatting import compact_decimal

ZERO = Decimal("0")
HUNDRED = Decimal("100")
PLOT_TOP = Decimal("8")
PLOT_HEIGHT = Decimal("84")


def build_price_points(
    symbol: str,
    daily_bars: Sequence[Mapping[str, object]],
) -> tuple[PricePoint, ...]:
    rows = sorted(
        (row for row in daily_bars if str(row.get("symbol")) == symbol),
        key=lambda row: _date(row.get("trade_date")),
    )
    if not rows:
        return ()
    prices = [_decimal(row.get("close")) for row in rows]
    low = min(prices)
    high = max(prices)
    count = len(rows)
    return tuple(
        PricePoint(
            date=_date(row.get("trade_date")),
            label=_date(row.get("trade_date")).strftime("%b %d"),
            price=price,
            x_percent=(
                Decimal(index) / Decimal(count - 1) * HUNDRED if count > 1 else ZERO
            ),
            y_percent=_y_percent(price, low=low, high=high),
            is_friday=_date(row.get("trade_date")).weekday() == 4,
        )
        for index, (row, price) in enumerate(zip(rows, prices, strict=True))
    )


def build_option_events(
    symbol: str,
    *,
    executions: Sequence[Mapping[str, object]],
    lifecycle_events: Sequence[Mapping[str, object]],
    points: Sequence[PricePoint],
    current_option_symbols: set[str],
) -> tuple[PriceEvent, ...]:
    if not points:
        return ()
    start, end = points[0].date, points[-1].date
    option_rows = [
        _execution_event(row, symbol=symbol, points=points)
        for row in executions
        if _is_chart_option_execution(row, symbol=symbol, start=start, end=end)
    ]
    lifecycle_rows = [
        _lifecycle_event(row, symbol=symbol, points=points)
        for row in lifecycle_events
        if _is_chart_lifecycle(row, symbol=symbol, start=start, end=end)
    ]
    rows = [row for row in (*option_rows, *lifecycle_rows) if row is not None]
    rows.sort(key=lambda row: (row["date"], row["sort_order"], row["stable_key"]))
    _mark_roll_openings(rows)
    _link_contract_lifecycles(rows)
    _assign_collision_offsets(rows)

    events: list[PriceEvent] = []
    for sequence, row in enumerate(rows, 1):
        row["sequence"] = sequence
    _replace_link_indexes_with_sequences(rows)
    for row in rows:
        event_date = _date(row["date"])
        option_symbol = str(row["option_symbol"])
        outcome = str(row["outcome"])
        if row["event_type"] in {"sale", "rolled"} and option_symbol in current_option_symbols:
            outcome = "OPEN"
        events.append(
            PriceEvent(
                sequence=_int(row["sequence"]),
                lifecycle_id=_int(row["sequence"]),
                record_id=str(row["stable_key"]),
                campaign_id=str(row.get("order_key") or row["stable_key"]),
                date=event_date,
                label=event_date.strftime("%m/%d"),
                event_type=str(row["event_type"]),
                glyph=str(row["glyph"]),
                detail=str(row["detail"]),
                price=_decimal(row["price"]),
                x_percent=_decimal(row["x_percent"]),
                y_percent=_decimal(row["y_percent"]),
                vertical_offset=_int(row["vertical_offset"]),
                linked_sale_sequence=_optional_int(row.get("linked_sale_sequence")),
                linked_resolution_sequence=_optional_int(
                    row.get("linked_resolution_sequence")
                ),
                resolved_on=_optional_date(row.get("resolved_on")),
                underlying_at_resolution=_optional_decimal(
                    row.get("underlying_at_resolution")
                ),
                expires_on=_date(row["expires_on"]),
                contracts=_int(row["contracts"]),
                strike=_decimal(row["strike"]),
                underlying_at_sale=_decimal(row["underlying_at_sale"]),
                strike_upside_percent=_decimal(row["strike_upside_percent"]),
                entry_days_to_expiration=_int(row["entry_days_to_expiration"]),
                premium_per_share=_decimal(row["premium_per_share"]),
                gross_premium=_decimal(row["gross_premium"]),
                buyback_cost=_decimal(row["buyback_cost"]),
                net_cash=_decimal(row["net_cash"]),
                outcome=outcome,
            )
        )
    return tuple(events)


def build_share_trade_events(
    symbol: str,
    *,
    executions: Sequence[Mapping[str, object]],
    points: Sequence[PricePoint],
) -> tuple[ShareTradeEvent, ...]:
    if not points:
        return ()
    start, end = points[0].date, points[-1].date
    events: list[ShareTradeEvent] = []
    for row in executions:
        occurred_on = _row_date(row)
        if not (
            start <= occurred_on <= end
            and str(row.get("asset_type")) != "option"
            and str(row.get("symbol")) == symbol
            and str(row.get("side")) in {"buy", "sell"}
        ):
            continue
        price = _decimal(row.get("price"))
        x, y = _coordinates(occurred_on, price, points)
        action = str(row.get("side"))
        events.append(
            ShareTradeEvent(
                date=occurred_on,
                label=occurred_on.strftime("%m/%d"),
                action=action,
                glyph="+" if action == "buy" else "-",
                shares=int(_decimal(row.get("quantity"))),
                price=price,
                x_percent=x,
                y_percent=y,
            )
        )
    return tuple(events)


def _execution_event(
    row: Mapping[str, object],
    *,
    symbol: str,
    points: Sequence[PricePoint],
) -> dict[str, object] | None:
    opening = str(row.get("side")) == "sell" and str(row.get("position_effect")) == "opening"
    closing = str(row.get("side")) == "buy" and str(row.get("position_effect")) == "closing"
    if not (opening or closing):
        return None
    occurred_on = _row_date(row)
    stock_price = _price_on_or_before(occurred_on, points)
    strike = _decimal(row.get("strike"))
    expires_on = _date(row.get("expiration_date"))
    x, y = _coordinates(occurred_on, stock_price, points)
    contracts = int(_decimal(row.get("quantity")))
    return {
        "stable_key": str(row.get("external_key")),
        "order_key": str(row.get("order_external_key") or ""),
        "option_symbol": str(row.get("symbol")),
        "date": occurred_on,
        "sort_order": 0 if closing else 1,
        "event_type": "sale" if opening else "closed",
        "glyph": "S" if opening else "C",
        "detail": (
            f"Sold {contracts}x ${compact_decimal(strike)}C / "
            f"{max(0, (expires_on - occurred_on).days)} DTE"
            if opening
            else f"Closed {contracts}x ${compact_decimal(strike)}C"
        ),
        "price": stock_price,
        "x_percent": x,
        "y_percent": y,
        "expires_on": expires_on,
        "contracts": contracts,
        "strike": strike,
        "underlying_at_sale": stock_price,
        "strike_upside_percent": (
            (strike / stock_price - Decimal("1")) * HUNDRED if stock_price else ZERO
        ),
        "entry_days_to_expiration": max(0, (expires_on - occurred_on).days),
        "premium_per_share": _decimal(row.get("price")),
        "gross_premium": _decimal(row.get("gross_amount")) if opening else ZERO,
        "buyback_cost": _decimal(row.get("gross_amount")) if closing else ZERO,
        "net_cash": _decimal(row.get("net_cash")),
        "outcome": "OPEN" if opening else "CLOSED",
        "vertical_offset": 0,
    }


def _lifecycle_event(
    row: Mapping[str, object],
    *,
    symbol: str,
    points: Sequence[PricePoint],
) -> dict[str, object] | None:
    event_type = str(row.get("event_type"))
    if event_type not in {"expiration", "assignment"}:
        return None
    occurred_on = _row_date(row)
    stock_price = _price_on_or_before(occurred_on, points)
    strike = _decimal(row.get("strike"))
    expires_on = _date(row.get("expiration_date") or occurred_on)
    x, y = _coordinates(occurred_on, stock_price, points)
    contracts = int(_decimal(row.get("option_quantity")))
    return {
        "stable_key": str(row.get("external_key")),
        "order_key": "",
        "option_symbol": str(row.get("symbol")),
        "date": occurred_on,
        "sort_order": 2,
        "event_type": "expired" if event_type == "expiration" else "assigned",
        "glyph": "X" if event_type == "expiration" else "A",
        "detail": (
            f"Expired {contracts}x ${compact_decimal(strike)}C"
            if event_type == "expiration"
            else f"Assigned {contracts}x ${compact_decimal(strike)}C"
        ),
        "price": stock_price,
        "x_percent": x,
        "y_percent": y,
        "expires_on": expires_on,
        "contracts": contracts,
        "strike": strike,
        "underlying_at_sale": stock_price,
        "strike_upside_percent": (
            (strike / stock_price - Decimal("1")) * HUNDRED if stock_price else ZERO
        ),
        "entry_days_to_expiration": 0,
        "premium_per_share": ZERO,
        "gross_premium": ZERO,
        "buyback_cost": ZERO,
        "net_cash": ZERO,
        "outcome": "EXPIRED" if event_type == "expiration" else "ASSIGNED",
        "vertical_offset": 0,
    }


def _mark_roll_openings(rows: list[dict[str, object]]) -> None:
    closing_orders = {
        str(row["order_key"])
        for row in rows
        if row["event_type"] == "closed" and row.get("order_key")
    }
    for row in rows:
        if row["event_type"] == "sale" and row.get("order_key") in closing_orders:
            row["event_type"] = "rolled"
            row["glyph"] = "R"
            row["detail"] = str(row["detail"]).replace("Sold", "Rolled to", 1)
            row["outcome"] = "ROLLED OPEN"


def _link_contract_lifecycles(rows: list[dict[str, object]]) -> None:
    open_sales: defaultdict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        option_symbol = str(row["option_symbol"])
        if row["event_type"] in {"sale", "rolled"}:
            open_sales[option_symbol].append(index)
            continue
        if row["event_type"] not in {"closed", "expired", "assigned"}:
            continue
        if not open_sales[option_symbol]:
            continue
        sale_index = open_sales[option_symbol].pop()
        sale = rows[sale_index]
        row["linked_sale_index"] = sale_index
        sale["linked_resolution_index"] = index
        sale["resolved_on"] = row["date"]
        sale["underlying_at_resolution"] = row["price"]
        sale["outcome"] = str(row["outcome"])
        row["underlying_at_sale"] = sale["underlying_at_sale"]
        row["strike_upside_percent"] = sale["strike_upside_percent"]
        row["entry_days_to_expiration"] = sale["entry_days_to_expiration"]
        row["premium_per_share"] = sale["premium_per_share"]
        row["gross_premium"] = sale["gross_premium"]
        row["underlying_at_resolution"] = row["price"]


def _replace_link_indexes_with_sequences(rows: list[dict[str, object]]) -> None:
    for row in rows:
        sale_index = row.pop("linked_sale_index", None)
        resolution_index = row.pop("linked_resolution_index", None)
        row["linked_sale_sequence"] = (
            _int(rows[_int(sale_index)]["sequence"]) if sale_index is not None else None
        )
        row["linked_resolution_sequence"] = (
            _int(rows[_int(resolution_index)]["sequence"])
            if resolution_index is not None
            else None
        )


def _assign_collision_offsets(rows: list[dict[str, object]]) -> None:
    lanes = (0, 18, -18, 36, -36)
    counts: defaultdict[date, int] = defaultdict(int)
    for row in rows:
        occurred_on = row["date"]
        lane = counts[occurred_on]  # type: ignore[index]
        row["vertical_offset"] = lanes[lane % len(lanes)]
        counts[occurred_on] += 1  # type: ignore[index]


def _is_chart_option_execution(
    row: Mapping[str, object], *, symbol: str, start: date, end: date
) -> bool:
    occurred_on = _row_date(row)
    return (
        start <= occurred_on <= end
        and str(row.get("asset_type")) == "option"
        and str(row.get("option_side")) == "call"
        and str(row.get("underlying_symbol")) == symbol
    )


def _is_chart_lifecycle(
    row: Mapping[str, object], *, symbol: str, start: date, end: date
) -> bool:
    occurred_on = _row_date(row)
    return (
        start <= occurred_on <= end
        and str(row.get("option_side")) == "call"
        and str(row.get("underlying_symbol")) == symbol
    )


def _coordinates(
    occurred_on: date,
    price: Decimal,
    points: Sequence[PricePoint],
) -> tuple[Decimal, Decimal]:
    start = points[0].date
    end = points[-1].date
    span = max(1, (end - start).days)
    x = Decimal((occurred_on - start).days) / Decimal(span) * HUNDRED
    low = min(point.price for point in points)
    high = max(point.price for point in points)
    return max(ZERO, min(HUNDRED, x)), _y_percent(price, low=low, high=high)


def _price_on_or_before(value: date, points: Sequence[PricePoint]) -> Decimal:
    eligible = [point.price for point in points if point.date <= value]
    return eligible[-1] if eligible else points[0].price


def _y_percent(price: Decimal, *, low: Decimal, high: Decimal) -> Decimal:
    if high == low:
        return Decimal("50")
    return PLOT_TOP + (high - price) / (high - low) * PLOT_HEIGHT


def _row_date(row: Mapping[str, object]) -> date:
    return _date(row.get("occurred_at"))


def _date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _optional_date(value: object) -> date | None:
    return None if value is None else _date(value)


def _decimal(value: object) -> Decimal:
    return ZERO if value is None else Decimal(str(value))


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _int(value: object) -> int:
    return int(str(value))


def _optional_int(value: object) -> int | None:
    return None if value is None else _int(value)
