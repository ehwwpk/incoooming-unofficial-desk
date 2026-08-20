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

ZERO = Decimal("0")
HUNDRED = Decimal("100")
CENT = Decimal("0.01")
STANDARD_MULTIPLIER = Decimal("100")


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
    roll_parent_by_order: dict[tuple[str, str], str] = {}
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
        cash = _decimal(row.get("net_cash") if kind == "close" else row.get("cash_amount"))
        consumed_ids = _consume(
            lots[position_key],
            consume_qty,
            cash=cash,
            occurred_on=_row_date(row),
            terminal=_terminal_for(kind, row, roll_orders),
        )
        order_key = str(row.get("order_external_key") or "")
        account = str(row.get("account_mask") or "")
        if kind == "close" and order_key and consumed_ids and (account, order_key) in roll_orders:
            roll_parent_by_order[(account, order_key)] = consumed_ids[0]

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
    roll_parent_by_order: Mapping[tuple[str, str], str],
) -> CallSaleRecord:
    row = lot.row
    record_id = campaign_record_key(row)
    annotation = ledger.annotation_for(record_id)
    sold_on = _row_date(row)
    expires_on = _date(row.get("expiration_date")) or sold_on
    strike = _decimal(row.get("strike"))
    contracts = int(_quantity(row, "quantity"))
    multiplier = _decimal(row.get("contract_multiplier")) or STANDARD_MULTIPLIER
    opening_cash = _decimal(row.get("net_cash"))
    symbol = str(row.get("underlying_symbol") or "").strip().upper()
    option_side = str(row.get("option_side") or "call").strip().upper() or "CALL"
    if option_side not in {"CALL", "PUT"}:
        option_side = "CALL"
    underlying_at_sale = _close_on_or_before(symbol, sold_on, daily_bars) or ZERO
    premium = (
        abs(opening_cash) / (Decimal(contracts) * multiplier) if contracts and multiplier else ZERO
    )
    account = str(row.get("account_mask") or "")
    order_key = str(row.get("order_external_key") or "")
    parent = roll_parent_by_order.get((account, order_key))
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
        gross_premium=opening_cash
        if opening_cash > ZERO
        else abs(_decimal(row.get("gross_amount"))),
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
    events: list[tuple[date, str, int, datetime, str, str, Mapping[str, object]]] = []
    for row in executions:
        if str(row.get("asset_type")) != "option":
            continue
        opening = str(row.get("side")) == "sell" and str(row.get("position_effect")) == "opening"
        closing = str(row.get("side")) == "buy" and str(row.get("position_effect")) == "closing"
        if not (opening or closing):
            continue
        occurred = _datetime(row.get("occurred_at"))
        events.append(
            (
                occurred.date(),
                _scoped_order_key(row),
                0 if closing else 1,
                occurred,
                campaign_record_key(row),
                "close" if closing else "open",
                row,
            )
        )
    for row in lifecycle_events:
        event_type = str(row.get("event_type") or "")
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
                event_type,
                row,
            )
        )
    events.sort()
    return tuple((kind, row) for *_, kind, row in events)


def _roll_order_keys(executions: Sequence[Mapping[str, object]]) -> set[tuple[str, str]]:
    grouped: defaultdict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in executions:
        order_key = str(row.get("order_external_key") or "")
        if not order_key or str(row.get("asset_type")) != "option":
            continue
        grouped[(str(row.get("account_mask") or ""), order_key)].append(row)
    keys: set[tuple[str, str]] = set()
    for key, rows in grouped.items():
        has_close = any(
            str(row.get("side")) == "buy" and str(row.get("position_effect")) == "closing"
            for row in rows
        )
        has_open = any(
            str(row.get("side")) == "sell" and str(row.get("position_effect")) == "opening"
            for row in rows
        )
        if has_close and has_open:
            keys.add(key)
    return keys


def _terminal_for(kind: str, row: Mapping[str, object], roll_orders: set[tuple[str, str]]) -> str:
    if kind == "expiration":
        return "Expired"
    if kind == "assignment":
        return "Assigned"
    order_key = str(row.get("order_external_key") or "")
    account = str(row.get("account_mask") or "")
    if (account, order_key) in roll_orders:
        return "Rolled"
    return "Closed"


def _gap_percent(spot: Decimal, strike: Decimal, option_side: str) -> Decimal:
    if spot <= ZERO:
        return ZERO
    raw = (
        (spot - strike) / spot * HUNDRED
        if option_side == "PUT"
        else (strike - spot) / spot * HUNDRED
    )
    return raw.quantize(CENT)


def _position_key(row: Mapping[str, object]) -> str:
    account = str(row.get("account_mask") or "default")
    return f"{account}:{_canonical(str(row.get('symbol') or ''))}"


def _scoped_order_key(row: Mapping[str, object]) -> str:
    order_key = str(row.get("order_external_key") or "")
    if not order_key:
        return ""
    return f"{row.get('account_mask') or 'default'}:{order_key}"


def _close_on_or_before(
    symbol: str,
    value: date,
    daily_bars: Sequence[Mapping[str, object]],
) -> Decimal | None:
    dated: list[tuple[date, Mapping[str, object]]] = []
    for row in daily_bars:
        if str(row.get("symbol")) != symbol:
            continue
        trade_date = _date(row.get("trade_date"))
        if trade_date is None or trade_date > value:
            continue
        dated.append((trade_date, row))
    if not dated:
        return None
    latest = max(dated, key=lambda item: item[0])[1]
    return _decimal(latest.get("close"))


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
        occurred = value
    elif isinstance(value, date):
        occurred = datetime(value.year, value.month, value.day)
    else:
        occurred = datetime.fromisoformat(str(value))
    return occurred.replace(tzinfo=None)


def _decimal(value: object) -> Decimal:
    return ZERO if value is None else Decimal(str(value))
