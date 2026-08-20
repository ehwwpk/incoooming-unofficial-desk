from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.market_time import market_date

ZERO = Decimal("0")
STANDARD_MULTIPLIER = Decimal("100")
STRIKE_TICK = Decimal("0.05")


def is_equity_execution(row: Mapping[str, Any]) -> bool:
    asset = str(row.get("asset_type") or "").lower()
    return asset in {"equity", "stock"} and asset != "option"


def execution_key(row: Mapping[str, Any]) -> str:
    return str(row.get("external_key") or id(row))


def classify_forced_equity(
    *,
    executions: Sequence[Mapping[str, Any]],
    lifecycle_events: Sequence[Mapping[str, Any]],
) -> tuple[frozenset[str], frozenset[tuple[str, date]]]:
    """Pair assignment/expiration stock legs. Uncertain symbol-days are not guessed."""

    equity = [row for row in executions if is_equity_execution(row)]
    forced: set[str] = set()
    uncertain: set[tuple[str, date]] = set()
    used: set[str] = set()
    for event in lifecycle_events:
        event_type = str(event.get("event_type") or "").lower()
        if event_type not in {"assignment", "expiration"}:
            continue
        day = _row_day(event)
        symbol = str(event.get("underlying_symbol") or event.get("symbol") or "").upper()
        if day is None or not symbol:
            continue
        candidates = [
            row
            for row in equity
            if execution_key(row) not in used
            and _row_day(row) == day
            and str(row.get("symbol") or "").upper() == symbol
            and _matches_forced_leg(event, row)
        ]
        if len(candidates) == 1:
            key = execution_key(candidates[0])
            forced.add(key)
            used.add(key)
            continue
        same_day_equity = [
            row
            for row in equity
            if execution_key(row) not in used
            and _row_day(row) == day
            and str(row.get("symbol") or "").upper() == symbol
        ]
        if same_day_equity:
            uncertain.add((symbol, day))
    return frozenset(forced), frozenset(uncertain)


def apply_discretionary_equity(
    quantities: dict[str, Decimal],
    cash: Decimal,
    *,
    executions: Sequence[Mapping[str, Any]],
    after: date,
    through: date,
    forced_keys: frozenset[str],
    uncertain_symbol_days: frozenset[tuple[str, date]],
    include_anchor: bool = False,
) -> tuple[dict[str, Decimal], Decimal, bool]:
    """Copy manual share trades into freeze lots and cash. Skip forced legs."""

    next_qty = dict(quantities)
    next_cash = cash
    omitted = False
    for row in executions:
        if not is_equity_execution(row):
            continue
        day = _row_day(row)
        if day is None:
            continue
        if include_anchor:
            if day > through or day < after:
                continue
        elif not (after < day <= through):
            continue
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        if (symbol, day) in uncertain_symbol_days:
            omitted = True
            continue
        if execution_key(row) in forced_keys:
            continue
        shares = _signed_shares(row)
        price = _decimal(row.get("price"))
        next_cash -= shares * price
        next_qty[symbol] = next_qty.get(symbol, ZERO) + shares
        if next_qty[symbol] <= ZERO:
            del next_qty[symbol]
    return next_qty, next_cash, omitted


def scaled_dividend(
    row: Mapping[str, Any],
    *,
    freeze_qty: Decimal,
    live_qty: Decimal | None,
) -> Decimal:
    if live_qty is None or live_qty <= ZERO or freeze_qty <= ZERO:
        return ZERO
    return _decimal(row.get("amount")) * freeze_qty / live_qty


def live_long_quantity(
    position_history: Sequence[Mapping[str, Any]],
    symbol: str,
    day: date,
) -> Decimal | None:
    grouped: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for row in position_history:
        if str(row.get("asset_type") or "").upper() == "OPTION":
            continue
        if str(row.get("symbol") or "").upper() != symbol:
            continue
        observed = row.get("observed_at")
        if observed is None:
            continue
        observed_day = market_date(observed) if isinstance(observed, datetime) else observed
        if not isinstance(observed_day, date) or observed_day > day:
            continue
        grouped[observed_day] += _decimal(row.get("net_quantity"))
    if not grouped:
        return None
    chosen = max(grouped)
    qty = grouped[chosen]
    return qty if qty > ZERO else ZERO


def _matches_forced_leg(event: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    option_side = str(event.get("option_side") or "").lower()
    side = str(row.get("side") or "").lower()
    if option_side == "call" and side != "sell":
        return False
    if option_side == "put" and side != "buy":
        return False
    if option_side not in {"call", "put"}:
        return False
    expected = _event_shares(event)
    got = abs(_decimal(row.get("quantity")))
    if expected <= ZERO or got != expected:
        return False
    strike = _optional(event.get("strike"))
    price = _optional(row.get("price"))
    if strike is None or price is None:
        return False
    return abs(price - strike) <= STRIKE_TICK


def _event_shares(event: Mapping[str, Any]) -> Decimal:
    stock = abs(_decimal(event.get("stock_quantity")))
    if stock:
        return stock
    multiplier = _decimal(event.get("contract_multiplier")) or STANDARD_MULTIPLIER
    return abs(_decimal(event.get("option_quantity"))) * multiplier


def _signed_shares(row: Mapping[str, Any]) -> Decimal:
    quantity = abs(_decimal(row.get("quantity")))
    side = str(row.get("side") or "").lower()
    if side == "sell":
        return -quantity
    return quantity


def _row_day(row: Mapping[str, Any]) -> date | None:
    value = row.get("occurred_at")
    if isinstance(value, datetime):
        return market_date(value)
    if isinstance(value, date):
        return value
    return None


def _optional(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _decimal(value: object) -> Decimal:
    return ZERO if value is None else Decimal(str(value))
