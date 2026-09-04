from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from schwab_dashboard.application.campaigns import (
    CampaignLedger,
    campaign_record_key,
    reconcile_option_campaigns,
)
from schwab_dashboard.application.dashboard.covered_calls import CallSaleRecord
from schwab_dashboard.application.market_time import ledger_market_datetime
from schwab_dashboard.application.option_lifecycle import (
    contract_multiplier,
    lifecycle_event_type,
)
from schwab_dashboard.application.option_lifecycle import option_side as normalized_option_side

ZERO = Decimal("0")
HUNDRED = Decimal("100")
CENT = Decimal("0.01")


@dataclass(slots=True)
class _OpenLot:
    row: Mapping[str, object]
    remaining: Decimal
    close_cash: Decimal = ZERO
    closed_on: date | None = None
    terminal: str | None = None


def project_call_sale_records(
    executions: Sequence[Mapping[str, object]],
    lifecycle_events: Sequence[Mapping[str, object]],
    *,
    daily_bars: Sequence[Mapping[str, object]] = (),
    as_of: date,
) -> tuple[CallSaleRecord, ...]:
    """Project each short opening fill into the existing ticket table schema.

    ``as_of`` is accepted so the live and CSV readers share a projector
    signature with campaign cards. Tickets do not infer expiration from the
    calendar; only a broker expiration or assignment event can leave Open.
    """

    _ = as_of
    ledger = reconcile_option_campaigns(executions, lifecycle_events)
    excluded = {item.record_key for item in ledger.exclusions}
    lots: defaultdict[str, list[_OpenLot]] = defaultdict(list)
    roll_parent_by_order: dict[tuple[str, str, str, str], str] = {}
    roll_orders = _roll_order_keys(executions)

    for kind, row in _timeline(executions, lifecycle_events, excluded):
        position_key = _position_key(row)
        if kind == "open":
            quantity = _quantity(row, "quantity")
            if quantity <= ZERO:
                continue
            lots[position_key].append(_OpenLot(row=row, remaining=quantity))
            continue
        consume_qty = (
            _quantity(row, "quantity") if kind == "close" else _quantity(row, "option_quantity")
        )
        # Stock delivery cash belongs to the assigned shares, not option premium.
        cash = _decimal(row.get("net_cash")) if kind == "close" else ZERO
        consumed_ids = _consume(
            lots[position_key],
            consume_qty,
            cash=cash,
            occurred_on=_row_date(row),
            terminal=_terminal_for(kind, row, roll_orders),
        )
        roll_key = _roll_key(row)
        if kind == "close" and roll_key[1] and consumed_ids and roll_key in roll_orders:
            roll_parent_by_order[roll_key] = consumed_ids[0]

    records = [
        _ticket(
            lot,
            ledger=ledger,
            daily_bars=daily_bars,
            roll_parent_by_order=roll_parent_by_order,
        )
        for queue in lots.values()
        for lot in queue
        if int(_quantity(lot.row, "quantity")) > 0
    ]
    return tuple(sorted(records, key=lambda item: (item.sold_on, item.record_id)))


def _ticket(
    lot: _OpenLot,
    *,
    ledger: CampaignLedger,
    daily_bars: Sequence[Mapping[str, object]],
    roll_parent_by_order: Mapping[tuple[str, str, str, str], str],
) -> CallSaleRecord:
    row = lot.row
    record_id = campaign_record_key(row)
    annotation = ledger.annotation_for(record_id)
    sold_on = _row_date(row)
    expires_on = _date(row.get("expiration_date")) or sold_on
    strike = _decimal(row.get("strike"))
    contracts = int(_quantity(row, "quantity"))
    multiplier = contract_multiplier(row)
    opening_cash = _decimal(row.get("net_cash"))
    symbol = str(row.get("underlying_symbol") or "").strip().upper()
    normalized_side = normalized_option_side(row.get("option_side"))
    option_side = normalized_side.upper() if normalized_side is not None else "OPTION"
    underlying_at_sale = _close_on_or_before(symbol, sold_on, daily_bars)
    scale = Decimal(contracts) * multiplier
    execution_price = _optional_decimal(row.get("price"))
    gross_amount = _optional_decimal(row.get("gross_amount"))
    premium = (
        abs(execution_price)
        if execution_price is not None
        else abs(gross_amount) / scale
        if gross_amount is not None and scale
        else abs(opening_cash) / scale
        if scale
        else ZERO
    )
    gross_premium = abs(gross_amount) if gross_amount is not None else premium * scale
    parent = roll_parent_by_order.get(_roll_key(row))
    if parent == record_id:
        parent = None
    buyback = -lot.close_cash if lot.close_cash < ZERO else ZERO
    outcome = "Open" if lot.remaining > ZERO else (lot.terminal or "Closed")
    return CallSaleRecord(
        record_id=record_id,
        campaign_id=annotation.campaign_id if annotation is not None else record_id,
        parent_record_id=parent,
        policy_id="",
        symbol=symbol or str(row.get("symbol") or "").strip().upper(),
        sold_on=sold_on,
        expires_on=expires_on,
        contracts=contracts,
        underlying_at_sale=underlying_at_sale,
        strike=strike,
        strike_upside_percent=_gap_percent(underlying_at_sale, strike, option_side),
        days_to_expiration=max(0, (expires_on - sold_on).days),
        premium_per_share=premium.quantize(CENT) if premium else ZERO,
        gross_premium=gross_premium,
        buyback_cost=buyback,
        net_cash=opening_cash + lot.close_cash,
        outcome=outcome,
        sale_signal="",
        closed_on=None if outcome == "Open" else lot.closed_on,
        fees=_decimal(row.get("fees")),
        option_side=option_side,
    )


def _consume(
    queue: list[_OpenLot],
    quantity: Decimal,
    *,
    cash: Decimal,
    occurred_on: date,
    terminal: str,
) -> tuple[str, ...]:
    if quantity <= ZERO or not queue:
        return ()
    remaining = quantity
    consumed_ids: list[str] = []
    for lot in queue:
        if remaining <= ZERO:
            break
        if lot.remaining <= ZERO:
            continue
        take = min(lot.remaining, remaining)
        lot.remaining -= take
        lot.close_cash += take / quantity * cash
        lot.closed_on = occurred_on
        remaining -= take
        consumed_ids.append(campaign_record_key(lot.row))
        if lot.remaining == ZERO:
            lot.terminal = terminal
    return tuple(consumed_ids)


def _timeline(
    executions: Sequence[Mapping[str, object]],
    lifecycle_events: Sequence[Mapping[str, object]],
    excluded: set[str],
) -> tuple[tuple[str, Mapping[str, object]], ...]:
    events: list[tuple[date, str, int, datetime, str, int, str, Mapping[str, object]]] = []
    for index, row in enumerate(executions):
        if _token(row.get("asset_type")) != "option":
            continue
        opening = _token(row.get("side")) in {"sell", "sold"} and _token(
            row.get("position_effect")
        ) in {"open", "opening"}
        closing = _token(row.get("side")) in {"buy", "bought"} and _token(
            row.get("position_effect")
        ) in {"close", "closing"}
        if (
            not (opening or closing)
            or normalized_option_side(row.get("option_side")) is None
            or campaign_record_key(row) in excluded
        ):
            continue
        occurred = _datetime(row.get("occurred_at"))
        events.append(
            (
                occurred.date(),
                _scoped_order_key(row),
                0 if closing else 1,
                occurred,
                campaign_record_key(row),
                index,
                "close" if closing else "open",
                row,
            )
        )
    for index, row in enumerate(lifecycle_events, start=len(executions)):
        event_type = lifecycle_event_type(row.get("event_type"))
        if event_type not in {"expiration", "assignment"}:
            continue
        if campaign_record_key(row) in excluded:
            continue
        occurred = _datetime(row.get("occurred_at"))
        events.append(
            (
                occurred.date(),
                "",
                2,
                occurred,
                campaign_record_key(row),
                index,
                event_type,
                row,
            )
        )
    events.sort()
    return tuple((kind, row) for *_, kind, row in events)


def _roll_order_keys(
    executions: Sequence[Mapping[str, object]],
) -> set[tuple[str, str, str, str]]:
    grouped: defaultdict[tuple[str, str, str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in executions:
        order_key = str(row.get("order_external_key") or "")
        if not order_key or _token(row.get("asset_type")) != "option":
            continue
        grouped[_roll_key(row)].append(row)
    keys: set[tuple[str, str, str, str]] = set()
    for key, rows in grouped.items():
        has_close = any(
            _token(row.get("side")) in {"buy", "bought"}
            and _token(row.get("position_effect")) in {"close", "closing"}
            for row in rows
        )
        has_open = any(
            _token(row.get("side")) in {"sell", "sold"}
            and _token(row.get("position_effect")) in {"open", "opening"}
            for row in rows
        )
        if has_close and has_open:
            keys.add(key)
    return keys


def _terminal_for(
    kind: str,
    row: Mapping[str, object],
    roll_orders: set[tuple[str, str, str, str]],
) -> str:
    if kind == "expiration":
        return "Expired"
    if kind == "assignment":
        return "Assigned"
    if _roll_key(row) in roll_orders:
        return "Rolled"
    return "Closed"


def _gap_percent(
    spot: Decimal | None,
    strike: Decimal,
    option_side: str,
) -> Decimal | None:
    if spot is None or spot <= ZERO:
        return None
    raw = (
        (spot - strike) / spot * HUNDRED
        if option_side == "PUT"
        else (strike - spot) / spot * HUNDRED
    )
    return raw.quantize(CENT)


def _position_key(row: Mapping[str, object]) -> str:
    return f"{_account_scope(row)}:{_canonical(str(row.get('symbol') or ''))}"


def _scoped_order_key(row: Mapping[str, object]) -> str:
    key = _roll_key(row)
    if not key[1]:
        return ""
    return ":".join(key)


def _roll_key(row: Mapping[str, object]) -> tuple[str, str, str, str]:
    return (
        _account_scope(row),
        str(row.get("order_external_key") or "").strip(),
        _canonical(str(row.get("underlying_symbol") or "")),
        normalized_option_side(row.get("option_side")) or "",
    )


def _account_scope(row: Mapping[str, object]) -> str:
    return str(row.get("account_id") or row.get("account_mask") or "default").strip().casefold()


def _close_on_or_before(
    symbol: str,
    value: date,
    daily_bars: Sequence[Mapping[str, object]],
) -> Decimal | None:
    dated: list[tuple[date, Mapping[str, object]]] = []
    for row in daily_bars:
        if _canonical(str(row.get("symbol") or "")) != _canonical(symbol):
            continue
        trade_date = _date(row.get("trade_date"))
        close = _optional_decimal(row.get("close"))
        if trade_date is None or trade_date > value or close is None or close <= ZERO:
            continue
        dated.append((trade_date, row))
    if not dated:
        return None
    latest = max(dated, key=lambda item: item[0])[1]
    return _optional_decimal(latest.get("close"))


def _quantity(row: Mapping[str, object], field_name: str) -> Decimal:
    return abs(_decimal(row.get(field_name)))


def _canonical(value: str) -> str:
    return "".join(value.upper().split())


def _row_date(row: Mapping[str, object]) -> date:
    return _datetime(row.get("occurred_at")).date()


def _date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return ledger_market_datetime(value)
    elif isinstance(value, date):
        return ledger_market_datetime(value)
    return _datetime(datetime.fromisoformat(str(value).replace("Z", "+00:00")))


def _decimal(value: object) -> Decimal:
    return ZERO if value is None else Decimal(str(value))


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _token(value: object) -> str:
    return str(value or "").strip().casefold().split(".")[-1]
