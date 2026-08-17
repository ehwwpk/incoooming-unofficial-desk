from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class RecentOptionActivityItem:
    event_id: str
    occurred_at: datetime
    occurred_on: date
    date_label: str
    symbol: str
    action_label: str
    detail: str
    amount: Decimal
    contracts: int
    tone: str
    anchor_id: str
    leg_count: int


@dataclass(frozen=True, slots=True)
class OptionOutcomeSummary:
    recorded_from: date | None
    recorded_through: date
    expired_contracts: int
    bought_back_contracts: int
    rolled_contracts: int
    roll_orders: int
    assigned_contracts: int
    assignment_shares: int
    open_call_contracts: int
    open_put_contracts: int

    @property
    def open_contracts(self) -> int:
        return self.open_call_contracts + self.open_put_contracts


def build_recent_option_activity(
    executions: Sequence[Mapping[str, object]],
    *,
    as_of: date,
    limit: int = 8,
) -> tuple[RecentOptionActivityItem, ...]:
    """Build a fill-aware option tape while presenting linked rolls as one action."""
    if limit < 1:
        return ()
    rows = tuple(row for row in executions if _is_option(row))
    groups: defaultdict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        order_key = str(row.get("order_external_key") or "").strip()
        external_key = str(row.get("external_key") or "unkeyed")
        symbol = _underlying(row)
        groups[(symbol, order_key or f"fill:{external_key}")].append(row)

    events: list[RecentOptionActivityItem] = []
    for (symbol, group_key), order_rows in groups.items():
        events.extend(_activity_for_group(symbol, group_key, order_rows, as_of=as_of))
    return tuple(
        sorted(events, key=lambda item: (item.occurred_at, item.event_id), reverse=True)[:limit]
    )


def build_option_outcomes(
    executions: Sequence[Mapping[str, object]],
    lifecycle_events: Sequence[Mapping[str, object]],
    *,
    as_of: date,
    open_call_contracts: int,
    open_put_contracts: int,
) -> OptionOutcomeSummary:
    """Count mutually understandable outcomes from auditable short-option events."""
    rows = tuple(row for row in executions if _is_option(row))
    opening_rows = tuple(row for row in rows if _is_opening_sale(row))
    closing_rows = tuple(row for row in rows if _is_closing_buy(row))
    rolled_contracts, roll_orders = _roll_totals(rows)
    closing_contracts = sum((_quantity(row) for row in closing_rows), 0)

    short_symbols = {str(row.get("symbol") or "").strip().upper() for row in opening_rows} - {""}
    resolved_rows = tuple(
        row
        for row in lifecycle_events
        if str(row.get("symbol") or "").strip().upper() in short_symbols
    )
    expired = sum(
        (_lifecycle_quantity(row) for row in resolved_rows if _event_type(row) == "expiration"),
        0,
    )
    assignments = tuple(row for row in resolved_rows if _event_type(row) == "assignment")
    assigned = sum((_lifecycle_quantity(row) for row in assignments), 0)
    assignment_shares = sum((abs(_integer(row.get("stock_quantity"))) for row in assignments), 0)

    dated_rows = (*rows, *resolved_rows)
    recorded_from = min((_row_datetime(row).date() for row in dated_rows), default=None)
    return OptionOutcomeSummary(
        recorded_from=recorded_from,
        recorded_through=as_of,
        expired_contracts=expired,
        bought_back_contracts=max(0, closing_contracts - rolled_contracts),
        rolled_contracts=rolled_contracts,
        roll_orders=roll_orders,
        assigned_contracts=assigned,
        assignment_shares=assignment_shares,
        open_call_contracts=open_call_contracts,
        open_put_contracts=open_put_contracts,
    )


def count_rolled_contracts(executions: Sequence[Mapping[str, object]]) -> int:
    return _roll_totals(tuple(row for row in executions if _is_option(row)))[0]


def _activity_for_group(
    symbol: str,
    group_key: str,
    rows: Sequence[Mapping[str, object]],
    *,
    as_of: date,
) -> tuple[RecentOptionActivityItem, ...]:
    closes = tuple(row for row in rows if _is_closing_buy(row))
    opens = tuple(row for row in rows if _is_opening_sale(row))
    if closes and opens and _roll_contracts(rows):
        latest = max(_row_datetime(row) for row in rows)
        side = _common_side(rows)
        contracts = _roll_contracts(rows)
        return (
            RecentOptionActivityItem(
                event_id=f"roll:{group_key}",
                occurred_at=latest,
                occurred_on=latest.date(),
                date_label=_date_label(latest.date(), as_of),
                symbol=symbol,
                action_label=f"ROLLED {side.upper()}",
                detail=f"{_leg_summary(closes)}  ->  {_leg_summary(opens)}",
                amount=sum((_decimal(row.get("net_cash")) for row in rows), ZERO),
                contracts=contracts,
                tone="roll",
                anchor_id=f"{symbol.lower()}-workspace",
                leg_count=len({_leg_identity(row) for row in rows}),
            ),
        )

    fills: defaultdict[tuple[object, ...], list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        fills[(*_leg_identity(row), str(row.get("side")), str(row.get("position_effect")))].append(
            row
        )
    result: list[RecentOptionActivityItem] = []
    for index, fill_rows in enumerate(fills.values(), start=1):
        row = max(fill_rows, key=_row_datetime)
        occurred_at = _row_datetime(row)
        action = _action_label(row)
        amount = sum((_decimal(item.get("net_cash")) for item in fill_rows), ZERO)
        contracts = sum((_quantity(item) for item in fill_rows), 0)
        result.append(
            RecentOptionActivityItem(
                event_id=f"{group_key}:{index}",
                occurred_at=occurred_at,
                occurred_on=occurred_at.date(),
                date_label=_date_label(occurred_at.date(), as_of),
                symbol=symbol,
                action_label=action,
                detail=f"{_contract_label(row)}  /  {contracts} {_contract_word(contracts)}",
                amount=amount,
                contracts=contracts,
                tone="credit" if amount > ZERO else "debit" if amount < ZERO else "neutral",
                anchor_id=f"{symbol.lower()}-workspace",
                leg_count=1,
            )
        )
    return tuple(result)


def _roll_totals(rows: Sequence[Mapping[str, object]]) -> tuple[int, int]:
    groups: defaultdict[tuple[str, str, str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        order_key = str(row.get("order_external_key") or "").strip()
        if not order_key:
            continue
        group_key = (
            str(row.get("account_mask") or ""),
            order_key,
            _underlying(row),
            _side(row),
        )
        groups[group_key].append(row)
    counts = tuple(_roll_contracts(group) for group in groups.values())
    return sum(counts), sum(count > 0 for count in counts)


def _roll_contracts(rows: Sequence[Mapping[str, object]]) -> int:
    closing = sum((_quantity(row) for row in rows if _is_closing_buy(row)), 0)
    opening = sum((_quantity(row) for row in rows if _is_opening_sale(row)), 0)
    return min(closing, opening)


def _leg_summary(rows: Sequence[Mapping[str, object]]) -> str:
    identities = {_leg_identity(row): row for row in rows}
    if len(identities) == 1:
        row = next(iter(identities.values()))
        quantity = sum((_quantity(item) for item in rows), 0)
        return f"{_contract_label(row)}  /  {quantity} {_contract_word(quantity)}"
    return f"{len(identities)} LEGS"


def _leg_identity(row: Mapping[str, object]) -> tuple[object, ...]:
    return (
        str(row.get("symbol") or ""),
        str(row.get("option_side") or ""),
        str(row.get("expiration_date") or ""),
        str(row.get("strike") or ""),
    )


def _contract_label(row: Mapping[str, object]) -> str:
    strike = _compact_decimal(_decimal(row.get("strike")))
    side = "C" if _side(row) == "call" else "P" if _side(row) == "put" else "OPT"
    expires = row.get("expiration_date")
    expiry = expires.strftime("%b %d").upper() if isinstance(expires, date) else "NO EXP"
    return f"${strike}{side} {expiry}"


def _action_label(row: Mapping[str, object]) -> str:
    side = _side(row).upper() or "OPTION"
    action = (str(row.get("side")), str(row.get("position_effect")))
    return {
        ("sell", "opening"): f"SOLD {side}",
        ("buy", "closing"): f"CLOSED {side}",
        ("buy", "opening"): f"BOUGHT {side}",
        ("sell", "closing"): f"SOLD TO CLOSE {side}",
    }.get(action, f"OPTION {str(row.get('side') or 'MOVE').upper()}")


def _date_label(value: date, as_of: date) -> str:
    if value == as_of:
        return "TODAY"
    if value == as_of - timedelta(days=1):
        return "YESTERDAY"
    return value.strftime("%b %d").upper()


def _common_side(rows: Sequence[Mapping[str, object]]) -> str:
    sides = {_side(row) for row in rows} - {""}
    return next(iter(sides)) if len(sides) == 1 else "OPTION"


def _underlying(row: Mapping[str, object]) -> str:
    return str(row.get("underlying_symbol") or row.get("symbol") or "OPTION").strip().upper()


def _side(row: Mapping[str, object]) -> str:
    return str(row.get("option_side") or "").strip().lower()


def _event_type(row: Mapping[str, object]) -> str:
    return str(row.get("event_type") or "").strip().lower()


def _is_option(row: Mapping[str, object]) -> bool:
    return str(row.get("asset_type") or "").strip().lower() == "option"


def _is_opening_sale(row: Mapping[str, object]) -> bool:
    return str(row.get("side")) == "sell" and str(row.get("position_effect")) == "opening"


def _is_closing_buy(row: Mapping[str, object]) -> bool:
    return str(row.get("side")) == "buy" and str(row.get("position_effect")) == "closing"


def _row_datetime(row: Mapping[str, object]) -> datetime:
    value = row.get("occurred_at")
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    raise ValueError("Option activity is missing its source timestamp")


def _quantity(row: Mapping[str, object]) -> int:
    return abs(_integer(row.get("quantity")))


def _lifecycle_quantity(row: Mapping[str, object]) -> int:
    return abs(_integer(row.get("option_quantity")))


def _integer(value: object) -> int:
    return int(_decimal(value))


def _decimal(value: object) -> Decimal:
    return ZERO if value is None else Decimal(str(value))


def _compact_decimal(value: Decimal) -> str:
    text = f"{value:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _contract_word(value: int) -> str:
    return "CONTRACT" if value == 1 else "CONTRACTS"
