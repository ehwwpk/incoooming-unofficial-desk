from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.market_time import market_date

ZERO = Decimal("0")
STANDARD_MULTIPLIER = Decimal("100")
STRIKE_TICK = Decimal("0.05")

EquityScope = tuple[str, str, date]
KeyedExecution = tuple[str, Mapping[str, Any]]


def is_equity_execution(row: Mapping[str, Any]) -> bool:
    asset = str(row.get("asset_type") or "").lower()
    return asset in {"equity", "stock"} and asset != "option"


def execution_keys(executions: Sequence[Mapping[str, Any]]) -> tuple[KeyedExecution, ...]:
    """Give every execution a stable key, including repeated identical rows.

    Broker keys remain readable when they are unique. Rows without one use a
    canonical content digest. If either base key occurs more than once, every
    occurrence receives a deterministic suffix based on its ledger order. Both
    forced-delivery classification and share replay call this over the complete
    sequence so filtering cannot shift those suffixes.
    """

    bases = tuple(_execution_key_base(row) for row in executions)
    totals = Counter(bases)
    occurrences: defaultdict[str, int] = defaultdict(int)
    keyed: list[KeyedExecution] = []
    for base, row in zip(bases, executions, strict=True):
        occurrences[base] += 1
        key = f"{base}:{occurrences[base]}" if totals[base] > 1 else base
        keyed.append((key, row))
    return tuple(keyed)


def classify_forced_equity(
    *,
    executions: Sequence[Mapping[str, Any]],
    lifecycle_events: Sequence[Mapping[str, Any]],
) -> tuple[frozenset[str], frozenset[EquityScope]]:
    """Pair assignment/exercise stock legs. Uncertain account-symbol-days are omitted."""

    equity = [item for item in execution_keys(executions) if is_equity_execution(item[1])]
    forced: set[str] = set()
    uncertain: set[EquityScope] = set()
    used: set[str] = set()
    for event in lifecycle_events:
        event_type = _forced_event_type(event.get("event_type"))
        if event_type is None:
            continue
        day = _row_day(event)
        symbol = _symbol(event.get("underlying_symbol") or event.get("symbol"))
        if day is None or not symbol:
            continue
        scope = (_account(event), symbol, day)
        same_scope = [item for item in equity if _execution_scope(item[1]) == scope]
        candidates = [
            item
            for item in same_scope
            if item[0] not in used and _matches_forced_leg(event_type, event, item[1])
        ]
        match = _unique_quantity_subset(candidates, _event_shares(event))
        if match is not None:
            keys = {item[0] for item in match}
            forced.update(keys)
            used.update(keys)
            continue
        if same_scope:
            uncertain.add(scope)
    return frozenset(forced), frozenset(uncertain)


def apply_discretionary_equity(
    quantities: dict[str, Decimal],
    cash: Decimal,
    *,
    executions: Sequence[Mapping[str, Any]],
    after: date,
    through: date,
    forced_keys: frozenset[str],
    uncertain_symbol_days: frozenset[EquityScope],
    include_anchor: bool = False,
) -> tuple[dict[str, Decimal], Decimal, bool]:
    """Copy manual share trades into freeze lots and cash. Skip forced legs."""

    next_qty = dict(quantities)
    next_cash = cash
    omitted = False
    for key, row in execution_keys(executions):
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
        symbol = _symbol(row.get("symbol"))
        if not symbol:
            continue
        if (_account(row), symbol, day) in uncertain_symbol_days:
            omitted = True
            continue
        if key in forced_keys:
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
    snapshots: dict[tuple[str, str, str], Decimal] = defaultdict(lambda: ZERO)
    snapshot_order: dict[tuple[str, str, str], tuple[date, str, str]] = {}
    for row in position_history:
        observed = row.get("observed_at")
        if observed is None:
            continue
        observed_day = market_date(observed) if isinstance(observed, datetime) else observed
        if not isinstance(observed_day, date) or observed_day > day:
            continue
        account = _account(row) or "account"
        observed_key = (
            observed.isoformat() if isinstance(observed, (date, datetime)) else str(observed)
        )
        run_key = str(row.get("sync_run_id") or "")
        snapshot_key = (account, observed_key, run_key)
        # Seeing any position proves this account snapshot exists.  Initialize
        # it even when the target symbol is absent, because absence from a
        # complete later snapshot means the shares were sold, not that the last
        # non-zero quantity should be carried forever.
        snapshots[snapshot_key] += ZERO
        if (
            str(row.get("asset_type") or "").upper() != "OPTION"
            and str(row.get("symbol") or "").upper() == symbol
        ):
            snapshots[snapshot_key] += _decimal(row.get("net_quantity"))
        snapshot_order[snapshot_key] = (observed_day, observed_key, run_key)
    if not snapshots:
        return None
    latest_by_account: dict[str, tuple[tuple[date, str, str], Decimal]] = {}
    for snapshot_key, quantity in snapshots.items():
        account = snapshot_key[0]
        order = snapshot_order[snapshot_key]
        current = latest_by_account.get(account)
        if current is None or current[0] < order:
            latest_by_account[account] = (order, quantity)
    qty = sum((quantity for _order, quantity in latest_by_account.values()), ZERO)
    return qty if qty > ZERO else ZERO


def _matches_forced_leg(
    event_type: str,
    event: Mapping[str, Any],
    row: Mapping[str, Any],
) -> bool:
    expected_side = _delivery_side(event_type, event.get("option_side"))
    if expected_side is None or _execution_side(row.get("side")) != expected_side:
        return False
    strike = _optional(event.get("strike"))
    price = _optional(row.get("price"))
    if strike is None or price is None:
        return False
    return abs(price - strike) <= STRIKE_TICK


def _unique_quantity_subset(
    candidates: Sequence[KeyedExecution],
    expected: Decimal,
) -> tuple[KeyedExecution, ...] | None:
    """Return the only candidate subset totaling expected, or fail closed."""

    if expected <= ZERO:
        return None
    solutions: dict[Decimal, list[tuple[int, ...]]] = {ZERO: [()]}
    for index, (_, row) in enumerate(candidates):
        quantity = abs(_decimal(row.get("quantity")))
        if quantity <= ZERO or quantity > expected:
            continue
        previous = tuple((subtotal, tuple(paths)) for subtotal, paths in solutions.items())
        for subtotal, paths in previous:
            combined = subtotal + quantity
            if combined > expected:
                continue
            target = solutions.setdefault(combined, [])
            for path in paths:
                if len(target) >= 2:
                    break
                candidate_path = (*path, index)
                if candidate_path not in target:
                    target.append(candidate_path)
    matches = solutions.get(expected, [])
    if len(matches) != 1:
        return None
    return tuple(candidates[index] for index in matches[0])


def _event_shares(event: Mapping[str, Any]) -> Decimal:
    stock = abs(_decimal(event.get("stock_quantity")))
    if stock:
        return stock
    raw_multiplier = event.get("contract_multiplier")
    if raw_multiplier is None:
        raw_multiplier = event.get("multiplier")
    multiplier = STANDARD_MULTIPLIER if raw_multiplier is None else _decimal(raw_multiplier)
    return abs(_decimal(event.get("option_quantity"))) * multiplier


def _signed_shares(row: Mapping[str, Any]) -> Decimal:
    quantity = abs(_decimal(row.get("quantity")))
    side = _execution_side(row.get("side"))
    if side == "sell":
        return -quantity
    return quantity


def _execution_key_base(row: Mapping[str, Any]) -> str:
    external_key = str(row.get("external_key") or "").strip()
    if external_key:
        return external_key
    payload = json.dumps(
        _canonical_value(row),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"replay:{digest}"


def _canonical_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _forced_event_type(value: object) -> str | None:
    normalized = _normalized_token(value)
    if normalized in {"assignment", "assigned"}:
        return "assignment"
    if normalized in {"exercise", "exercised"}:
        return "exercise"
    return None


def _delivery_side(event_type: str, option_side: object) -> str | None:
    normalized_side = _option_side(option_side)
    if normalized_side is None:
        return None
    deliveries: dict[tuple[str, str], str] = {
        ("assignment", "call"): "sell",
        ("assignment", "put"): "buy",
        ("exercise", "call"): "buy",
        ("exercise", "put"): "sell",
    }
    return deliveries.get((event_type, normalized_side))


def _option_side(value: object) -> str | None:
    normalized = _normalized_token(value)
    if normalized in {"call", "c"}:
        return "call"
    if normalized in {"put", "p"}:
        return "put"
    return None


def _execution_side(value: object) -> str:
    normalized = _normalized_token(value)
    if normalized in {"sell", "sold"}:
        return "sell"
    if normalized in {"buy", "bought"}:
        return "buy"
    return normalized


def _normalized_token(value: object) -> str:
    return str(value or "").strip().casefold().split(".")[-1]


def _account(row: Mapping[str, Any]) -> str:
    return str(row.get("account_mask") or "").strip().casefold()


def _symbol(value: object) -> str:
    return str(value or "").strip().upper()


def _execution_scope(row: Mapping[str, Any]) -> EquityScope | None:
    day = _row_day(row)
    symbol = _symbol(row.get("symbol"))
    if day is None or not symbol:
        return None
    return (_account(row), symbol, day)


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
