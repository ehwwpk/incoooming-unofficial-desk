from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from itertools import pairwise
from typing import Any

from schwab_dashboard.application.market_time import MARKET_TIME_ZONE, market_date
from schwab_dashboard.application.option_lifecycle import (
    contract_multiplier,
    delivered_share_quantity,
    lifecycle_event_type,
    option_side,
)
from schwab_dashboard.application.performance.sessions import MarketCalendar
from schwab_dashboard.application.performance.share_replay import (
    classify_forced_equity_matches,
    forced_event_shares,
    lifecycle_event_keys,
)
from schwab_dashboard.application.values import optional_bool

ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")
RECONCILIATION_TOLERANCE_RATE = Decimal("0.0001")


@dataclass(slots=True)
class _Holding:
    symbol: str
    asset_type: str
    quantity: Decimal
    multiplier: Decimal
    market_value: Decimal | None
    underlying_symbol: str | None = None
    option_side: str | None = None
    expiration_date: date | None = None
    strike: Decimal | None = None
    is_non_standard: bool | None = None


@dataclass(frozen=True, slots=True)
class _Valuation:
    day: date
    value: Decimal | None
    coverage: Decimal
    estimated_symbols: tuple[str, ...]
    unresolved_symbols: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ActivityResult:
    residual: Decimal
    replay_valid: bool


def build_reconstructed_balance_history(
    *,
    balance_history: Sequence[dict[str, Any]],
    position_history: Sequence[dict[str, Any]],
    daily_bars: Sequence[dict[str, Any]],
    executions: Sequence[dict[str, Any]],
    cash_movements: Sequence[dict[str, Any]],
    lifecycle_events: Sequence[dict[str, Any]],
    calendar: MarketCalendar,
) -> tuple[dict[str, Any], ...]:
    """Insert auditable, bounded account valuations between broker anchors.

    Raw observations are returned unchanged. Synthetic rows exist only inside a
    pair of real account anchors with stable account coverage. Position and cash
    activity is replayed per account. When marks cannot be supported, the path
    falls back to a plainly labelled endpoint bridge rather than inventing a
    precise-looking portfolio valuation.
    """

    observed = _latest_observed_rows(balance_history, calendar=calendar)
    if len(observed) < 2:
        return tuple(balance_history)
    snapshots = _position_snapshots(position_history)
    bars = _bar_index(daily_bars)
    additions: list[dict[str, Any]] = []
    observed_days = sorted(observed)
    for left_day, right_day in pairwise(observed_days):
        missing_days = calendar.sessions_between(left_day, right_day, include_end=False)
        if not missing_days:
            continue
        left_accounts = frozenset(observed[left_day])
        right_accounts = frozenset(observed[right_day])
        if left_accounts != right_accounts:
            continue
        include_unscoped = len(left_accounts) == 1
        if not include_unscoped:
            left_boundary = min(
                _timestamp(row.get("observed_at")) for row in observed[left_day].values()
            )
            right_boundary = max(
                _timestamp(row.get("observed_at")) for row in observed[right_day].values()
            )
            if any(
                _has_unscoped_activity(rows, after=left_boundary, through=right_boundary)
                for rows in (executions, cash_movements, lifecycle_events)
            ):
                # Accountless activity cannot be allocated safely across several
                # brokerage accounts. Keep the gap unresolved instead of assigning
                # it to every account, no account, or an arbitrary account.
                continue
        for account in sorted(left_accounts):
            left = observed[left_day][account]
            right = observed[right_day][account]
            left_value = _optional_decimal(left.get("liquidation_value"))
            right_value = _optional_decimal(right.get("liquidation_value"))
            if left_value is None or right_value is None:
                continue
            additions.extend(
                _reconstruct_account_gap(
                    account=account,
                    left_day=left_day,
                    right_day=right_day,
                    missing_days=missing_days,
                    left_value=left_value,
                    right_value=right_value,
                    left_row=left,
                    right_row=right,
                    snapshots=snapshots,
                    bars=bars,
                    executions=executions,
                    cash_movements=cash_movements,
                    lifecycle_events=lifecycle_events,
                    calendar=calendar,
                    include_unscoped=include_unscoped,
                )
            )
    return tuple((*balance_history, *additions))


def _reconstruct_account_gap(
    *,
    account: str,
    left_day: date,
    right_day: date,
    missing_days: tuple[date, ...],
    left_value: Decimal,
    right_value: Decimal,
    left_row: Mapping[str, Any],
    right_row: Mapping[str, Any],
    snapshots: Mapping[tuple[str, str], tuple[dict[str, Any], ...]],
    bars: Mapping[tuple[str, date], Decimal],
    executions: Sequence[Mapping[str, Any]],
    cash_movements: Sequence[Mapping[str, Any]],
    lifecycle_events: Sequence[Mapping[str, Any]],
    calendar: MarketCalendar,
    include_unscoped: bool,
) -> list[dict[str, Any]]:
    left_positions = _positions_for_anchor(
        snapshots,
        account=account,
        anchor=left_row,
        day=left_day,
    )
    right_positions = _positions_for_anchor(
        snapshots,
        account=account,
        anchor=right_row,
        day=right_day,
    )
    holdings, holdings_unambiguous = _holdings(left_positions)
    anchor_complete = holdings_unambiguous and all(
        row.get("market_value") is not None
        and (
            _asset_type(row.get("asset_type")) != "option"
            or (
                optional_bool(row.get("is_non_standard")) is False
                and (
                    row.get("contract_multiplier") is not None or row.get("multiplier") is not None
                )
            )
        )
        for row in left_positions
    )
    residual = left_value - sum((_decimal(row.get("market_value")) for row in left_positions), ZERO)
    anchor_marks = _anchor_marks(left_positions, right_positions, left_day, right_day)
    account_executions = _account_rows(executions, account, include_unscoped=include_unscoped)
    marks = _merge_marks(_execution_marks(account_executions), anchor_marks)
    account_movements = _account_rows(cash_movements, account, include_unscoped=include_unscoped)
    account_lifecycle = _account_rows(lifecycle_events, account, include_unscoped=include_unscoped)
    left_at = _timestamp(left_row.get("observed_at"))
    right_at = _timestamp(right_row.get("observed_at"))
    _forced_keys, uncertain_scopes, matched_delivery_events = classify_forced_equity_matches(
        executions=account_executions,
        lifecycle_events=account_lifecycle,
    )
    keyed_lifecycle = lifecycle_event_keys(account_lifecycle)
    ambiguous_delivery = any(
        left_day <= scope[2] <= right_day for scope in uncertain_scopes
    ) or any(
        _incomplete_delivery_in_window(row, after=left_at, through=right_at)
        for event_key, row in keyed_lifecycle
        if event_key not in matched_delivery_events
    )
    days = (*missing_days, right_day)
    raw: list[_Valuation] = []
    previous_at = left_at
    replay_valid = True
    for day in days:
        through_at = right_at if day == right_day else _market_close(day)
        activity = _apply_activity(
            holdings,
            residual,
            after=previous_at,
            through=through_at,
            executions=account_executions,
            cash_movements=account_movements,
            lifecycle_events=keyed_lifecycle,
            matched_delivery_events=matched_delivery_events,
        )
        residual = activity.residual
        replay_valid = replay_valid and activity.replay_valid
        valuation = _value_holdings(
            holdings,
            residual=residual,
            day=day,
            bars=bars,
            anchor_marks=marks,
            calendar=calendar,
        )
        if not anchor_complete or ambiguous_delivery:
            valuation = _Valuation(
                day=day,
                value=None,
                coverage=ZERO,
                estimated_symbols=(),
                unresolved_symbols=tuple(sorted(holdings)),
            )
        raw.append(valuation)
        previous_at = through_at

    replay_valid = replay_valid and _holdings_match_right_anchor(holdings, right_positions)
    raw_complete = all(valuation.value is not None for valuation in raw)
    raw_terminal = raw[-1].value
    correction = (
        right_value - raw_terminal
        if replay_valid and raw_complete and raw_terminal is not None
        else None
    )
    bridge = (
        {}
        if correction is not None
        else _endpoint_bridge_path(
            left_at=left_at,
            right_at=right_at,
            days=days,
            left_value=left_value,
            right_value=right_value,
            cash_movements=account_movements,
        )
    )
    total_steps = Decimal(len(days))
    result: list[dict[str, Any]] = []
    for index, valuation in enumerate(raw[:-1], start=1):
        weight = Decimal(index) / total_steps
        if valuation.value is None or correction is None:
            value = bridge[valuation.day]
            quality = "estimated"
            subtype = "endpoint_bridge"
            adjustment = value - valuation.value if valuation.value is not None else ZERO
            coverage = valuation.coverage
            estimated = tuple(
                sorted(set(valuation.estimated_symbols) | set(valuation.unresolved_symbols))
            )
        else:
            adjustment = correction * weight
            value = valuation.value + adjustment
            material = abs(correction) > max(
                Decimal("5"), abs(right_value) * RECONCILIATION_TOLERANCE_RATE
            )
            is_estimated = bool(valuation.estimated_symbols) or material
            quality = "estimated" if is_estimated else "derived"
            subtype = "anchor_reconciled" if material else "position_replay"
            coverage = valuation.coverage
            estimated = valuation.estimated_symbols
        result.append(
            {
                "account_id": account,
                "account_mask": str(left_row.get("account_mask") or account),
                "observed_at": _market_close(valuation.day),
                "liquidation_value": value,
                "valuation_quality": quality,
                "valuation_subtype": subtype,
                "price_coverage_percent": coverage,
                "estimated_symbols": estimated,
                "reconciliation_adjustment": adjustment,
                "raw_reconstructed_value": valuation.value,
                "anchor_start": left_day,
                "anchor_end": right_day,
                "synthetic": True,
            }
        )
    return result


def _apply_activity(
    holdings: dict[str, _Holding],
    residual: Decimal,
    *,
    after: datetime,
    through: datetime,
    executions: Sequence[Mapping[str, Any]],
    cash_movements: Sequence[Mapping[str, Any]],
    lifecycle_events: Sequence[tuple[str, Mapping[str, Any]]],
    matched_delivery_events: frozenset[str],
) -> _ActivityResult:
    events: list[tuple[datetime, int, str, int, str, Mapping[str, Any], str | None]] = []
    kinds_by_instant_and_symbol: defaultdict[tuple[datetime, str], set[str]] = defaultdict(set)
    execution_session_symbols: set[tuple[date, str]] = set()
    imprecise_lifecycle_session_symbols: set[tuple[date, str]] = set()
    for index, row in enumerate(executions):
        occurred_at = _activity_timestamp(row.get("occurred_at"))
        if occurred_at is None or not after < occurred_at <= through:
            continue
        symbol = _symbol(row.get("symbol"))
        events.append(
            (
                occurred_at,
                0,
                _execution_order_key(row),
                index,
                "execution",
                row,
                None,
            )
        )
        if symbol:
            kinds_by_instant_and_symbol[(occurred_at, symbol)].add("execution")
            execution_session_symbols.add((market_date(occurred_at), symbol))
    for index, (lifecycle_key, row) in enumerate(lifecycle_events):
        occurred_at = _activity_timestamp(row.get("occurred_at"))
        if occurred_at is None or not after < occurred_at <= through:
            continue
        symbol = _symbol(row.get("symbol"))
        events.append((occurred_at, 1, lifecycle_key, index, "lifecycle", row, lifecycle_key))
        if symbol:
            kinds_by_instant_and_symbol[(occurred_at, symbol)].add("lifecycle")
            if occurred_at.astimezone(MARKET_TIME_ZONE).time() == time.min:
                imprecise_lifecycle_session_symbols.add((market_date(occurred_at), symbol))

    # Equal source timestamps do not establish whether a trade preceded a
    # lifecycle event for the same contract. Keep processing deterministic, but
    # do not certify the replay as position-derived when that ordering matters.
    replay_valid = not any(
        len(kinds) > 1 for kinds in kinds_by_instant_and_symbol.values()
    ) and execution_session_symbols.isdisjoint(imprecise_lifecycle_session_symbols)
    for _occurred_at, _kind_order, _order_key, _index, kind, row, event_key in sorted(events):
        if kind == "lifecycle":
            symbol = _symbol(row.get("symbol"))
            event_type = lifecycle_event_type(row.get("event_type"))
            if event_type not in {"assignment", "exercise", "expiration"}:
                continue
            holding = holdings.get(symbol)
            amount = abs(_decimal(row.get("option_quantity")))
            if amount:
                if (
                    holding is None
                    or holding.asset_type != "option"
                    or amount > abs(holding.quantity)
                ):
                    replay_valid = False
                else:
                    holding.quantity += -amount if holding.quantity > ZERO else amount
                    holding.market_value = None
                    if holding.quantity == ZERO:
                        del holdings[symbol]
            delivery_was_executed = event_key in matched_delivery_events
            cash_amount = _optional_decimal(row.get("cash_amount"))
            if cash_amount is not None and not delivery_was_executed:
                residual += cash_amount
            stock_quantity = forced_event_shares(row)
            stock_symbol = _symbol(row.get("stock_symbol") or row.get("underlying_symbol"))
            if (
                event_type in {"assignment", "exercise"}
                and stock_quantity
                and stock_symbol
                and not delivery_was_executed
            ):
                side = _delivery_side(event_type, row.get("option_side"))
                if side is not None:
                    signed = stock_quantity if side == "buy" else -stock_quantity
                    stock = holdings.get(stock_symbol)
                    if stock is None:
                        stock = _Holding(
                            symbol=stock_symbol,
                            asset_type="equity",
                            quantity=ZERO,
                            multiplier=ONE,
                            market_value=None,
                        )
                        holdings[stock_symbol] = stock
                    stock.quantity += signed
                    stock.market_value = None
                    if stock.quantity == ZERO:
                        del holdings[stock_symbol]
                    if cash_amount is None and row.get("strike") is not None:
                        residual -= signed * _decimal(row.get("strike"))
            continue

        symbol = _symbol(row.get("symbol"))
        if not symbol:
            continue
        asset_type = _asset_type(row.get("asset_type"))
        side = _token(row.get("side"))
        quantity = abs(_decimal(row.get("quantity")))
        if (
            asset_type not in {"equity", "option"}
            or side not in {"buy", "bought", "sell", "sold"}
            or quantity == ZERO
        ):
            replay_valid = False
            continue
        signed_quantity = -quantity if side in {"sell", "sold"} else quantity
        holding = holdings.get(symbol)
        multiplier = _execution_multiplier(row, asset_type=asset_type, holding=holding)
        if multiplier is None:
            replay_valid = False
            continue
        net_cash = _optional_decimal(row.get("net_cash"))
        if net_cash is None:
            price = _optional_decimal(row.get("price"))
            if price is None or price < ZERO:
                replay_valid = False
                continue
            net_cash = -signed_quantity * price * multiplier
            net_cash -= abs(_decimal(row.get("fees")))
        if holding is None:
            holding = _holding_from_row(row, quantity=ZERO, multiplier=multiplier)
            holdings[symbol] = holding
        elif holding.asset_type != asset_type:
            replay_valid = False
            continue
        holding.quantity += signed_quantity
        holding.market_value = None
        if holding.quantity == ZERO:
            del holdings[symbol]
        residual += net_cash

    for row in cash_movements:
        occurred_at = _activity_timestamp(row.get("occurred_at"))
        if occurred_at is not None and after < occurred_at <= through:
            residual += _decimal(row.get("amount"))
    return _ActivityResult(residual=residual, replay_valid=replay_valid)


def _value_holdings(
    holdings: Mapping[str, _Holding],
    *,
    residual: Decimal,
    day: date,
    bars: Mapping[tuple[str, date], Decimal],
    anchor_marks: Mapping[str, tuple[tuple[date, Decimal], ...]],
    calendar: MarketCalendar,
) -> _Valuation:
    value = residual
    priced_weight = ZERO
    total_weight = ZERO
    estimated: set[str] = set()
    unresolved: set[str] = set()
    for holding in holdings.values():
        weight = abs(
            holding.market_value
            if holding.market_value is not None
            else holding.quantity * holding.multiplier
        )
        total_weight += weight
        mark, is_estimated = _mark_on(
            holding,
            day=day,
            bars=bars,
            anchor_marks=anchor_marks,
            calendar=calendar,
        )
        if mark is None:
            unresolved.add(holding.symbol)
            continue
        priced_weight += weight
        if is_estimated:
            estimated.add(holding.symbol)
        value += holding.quantity * holding.multiplier * mark
    coverage = HUNDRED if total_weight == ZERO else priced_weight / total_weight * HUNDRED
    return _Valuation(
        day=day,
        value=None if unresolved else value,
        coverage=coverage,
        estimated_symbols=tuple(sorted(estimated)),
        unresolved_symbols=tuple(sorted(unresolved)),
    )


def _mark_on(
    holding: _Holding,
    *,
    day: date,
    bars: Mapping[tuple[str, date], Decimal],
    anchor_marks: Mapping[str, tuple[tuple[date, Decimal], ...]],
    calendar: MarketCalendar,
) -> tuple[Decimal | None, bool]:
    if holding.asset_type == "option" and holding.is_non_standard is not False:
        return None, True
    # Once a contract is past expiration, a stale or malformed broker bar must
    # not resurrect it. The expiration-day close remains eligible because the
    # contract can retain value through that session.
    if (
        holding.asset_type == "option"
        and holding.expiration_date is not None
        and day > holding.expiration_date
    ):
        return ZERO, False
    exact = bars.get((holding.symbol, day))
    if exact is not None:
        if holding.asset_type != "option" and exact <= ZERO:
            return None, True
        return _bounded_option_mark(holding, day, exact, bars), False
    observations = list(anchor_marks.get(holding.symbol, ()))
    observations.extend(
        (bar_day, close) for (symbol, bar_day), close in bars.items() if symbol == holding.symbol
    )
    if holding.asset_type != "option":
        observations = [(bar_day, close) for bar_day, close in observations if close > ZERO]
    by_day = {bar_day: close for bar_day, close in observations}
    if day in by_day:
        return _bounded_option_mark(holding, day, by_day[day], bars), True
    prior = max((bar_day for bar_day in by_day if bar_day < day), default=None)
    following = min((bar_day for bar_day in by_day if bar_day > day), default=None)
    if prior is not None and following is not None:
        span = max(1, calendar.session_span(prior, following))
        offset = calendar.session_span(prior, day)
        mark = by_day[prior] + (by_day[following] - by_day[prior]) * Decimal(offset) / Decimal(span)
        return _bounded_option_mark(holding, day, mark, bars), True
    if prior is not None and calendar.session_span(prior, day) <= 3:
        return _bounded_option_mark(holding, day, by_day[prior], bars), True
    return None, True


def _bounded_option_mark(
    holding: _Holding,
    day: date,
    mark: Decimal,
    bars: Mapping[tuple[str, date], Decimal],
) -> Decimal:
    if holding.asset_type != "option":
        return max(ZERO, mark)
    underlying = bars.get((_symbol(holding.underlying_symbol), day))
    strike = holding.strike
    side = _token(holding.option_side)
    if underlying is None or underlying <= ZERO or strike is None:
        return max(ZERO, mark)
    intrinsic = (
        max(ZERO, underlying - strike)
        if side in {"call", "c"}
        else max(ZERO, strike - underlying)
        if side in {"put", "p"}
        else ZERO
    )
    upper = underlying if side in {"call", "c"} else strike if side in {"put", "p"} else None
    bounded = max(intrinsic, mark)
    return min(bounded, upper) if upper is not None else bounded


def _endpoint_bridge_path(
    *,
    left_at: datetime,
    right_at: datetime,
    days: Sequence[date],
    left_value: Decimal,
    right_value: Decimal,
    cash_movements: Sequence[Mapping[str, Any]],
) -> dict[date, Decimal]:
    """Build a flow-aware constant-return path between immutable anchors.

    The bridge is explicitly an estimate, but it does not count owner funding as
    performance.  It solves for the one per-session return which, after applying
    transfers in their actual valuation interval, lands exactly on the closing
    broker anchor.
    """

    if not days:
        return {}
    flows: list[Decimal] = []
    previous = left_at
    for day in days:
        through = right_at if day == days[-1] else _market_close(day)
        flows.append(_cash_flow_between_instants(cash_movements, previous, through))
        previous = through

    def terminal(rate: Decimal) -> Decimal:
        value = left_value
        for flow in flows:
            value = value * (ONE + rate) + flow
        return value

    low = Decimal("-0.999999999")
    high = ONE
    low_value = terminal(low)
    high_value = terminal(high)
    while high_value < right_value and high < Decimal("1024"):
        high *= Decimal("2")
        high_value = terminal(high)
    if not low_value <= right_value <= high_value:
        return _linear_endpoint_bridge_path(
            left_value=left_value,
            right_value=right_value,
            days=days,
            flows=flows,
        )
    for _ in range(160):
        middle = (low + high) / Decimal("2")
        if terminal(middle) < right_value:
            low = middle
        else:
            high = middle
    rate = (low + high) / Decimal("2")
    values: dict[date, Decimal] = {}
    value = left_value
    for day, flow in zip(days, flows, strict=True):
        value = value * (ONE + rate) + flow
        values[day] = value
    values[days[-1]] = right_value
    return values


def _linear_endpoint_bridge_path(
    *,
    left_value: Decimal,
    right_value: Decimal,
    days: Sequence[date],
    flows: Sequence[Decimal],
) -> dict[date, Decimal]:
    """Conservative fallback for the rare bridge with no monotonic rate solution."""

    total_flow = sum(flows, ZERO)
    terminal_performance = right_value - total_flow
    span = Decimal(len(days))
    carried_flow = ZERO
    values: dict[date, Decimal] = {}
    for index, (day, flow) in enumerate(zip(days, flows, strict=True), start=1):
        carried_flow += flow
        weight = Decimal(index) / span
        values[day] = left_value + (terminal_performance - left_value) * weight + carried_flow
    values[days[-1]] = right_value
    return values


def _cash_flow_between_instants(
    rows: Sequence[Mapping[str, Any]], after: datetime, through: datetime
) -> Decimal:
    return sum(
        (
            _decimal(row.get("amount"))
            for row in rows
            if _token(row.get("movement_type")) == "transfer"
            and (occurred_at := _activity_timestamp(row.get("occurred_at"))) is not None
            and after < occurred_at <= through
        ),
        ZERO,
    )


def _latest_observed_rows(
    rows: Sequence[dict[str, Any]], *, calendar: MarketCalendar
) -> dict[date, dict[str, dict[str, Any]]]:
    cohorts: dict[date, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    legacy: dict[date, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        observed_at = row.get("observed_at")
        if not isinstance(observed_at, (date, datetime)):
            continue
        day = market_date(observed_at)
        if not calendar.is_session(day) or row.get("synthetic"):
            continue
        run_id = str(row.get("sync_run_id") or "")
        if run_id:
            cohorts[day][run_id].append(row)
            continue
        account = _account(row)
        current = legacy[day].get(account)
        if current is None or _timestamp(current.get("observed_at")) < _timestamp(observed_at):
            legacy[day][account] = row
    grouped = dict(legacy)
    for day, runs in cohorts.items():
        latest = max(
            runs.values(),
            key=lambda cohort: max(_timestamp(row.get("observed_at")) for row in cohort),
        )
        grouped[day] = {_account(row): row for row in latest}
    return grouped


def _position_snapshots(
    rows: Sequence[dict[str, Any]],
) -> dict[tuple[str, str], tuple[dict[str, Any], ...]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        account = _account(row)
        run = str(row.get("sync_run_id") or "")
        observed = _timestamp(row.get("observed_at")).isoformat()
        grouped[(account, run or observed)].append(row)
    return {key: tuple(value) for key, value in grouped.items()}


def _positions_for_anchor(
    snapshots: Mapping[tuple[str, str], tuple[dict[str, Any], ...]],
    *,
    account: str,
    anchor: Mapping[str, Any],
    day: date,
) -> tuple[dict[str, Any], ...]:
    run = str(anchor.get("sync_run_id") or "")
    if run and (account, run) in snapshots:
        return snapshots[(account, run)]
    candidates = [
        rows
        for (snapshot_account, _), rows in snapshots.items()
        if snapshot_account == account
        and rows
        and market_date(_timestamp(rows[0].get("observed_at"))) == day
        and _timestamp(rows[0].get("observed_at")) <= _timestamp(anchor.get("observed_at"))
    ]
    return max(candidates, key=lambda rows: _timestamp(rows[0].get("observed_at")), default=())


def _holdings(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, _Holding], bool]:
    result: dict[str, _Holding] = {}
    unambiguous = True
    for row in rows:
        quantity = _decimal(row.get("net_quantity"))
        symbol = _symbol(row.get("symbol"))
        if not symbol or quantity == ZERO:
            continue
        incoming = _holding_from_row(row, quantity=quantity)
        current = result.get(symbol)
        if current is None:
            result[symbol] = incoming
            continue
        if not _compatible_holdings(current, incoming):
            # A canonical symbol with conflicting contract metadata cannot be
            # valued safely. Retain deterministic state for diagnostics, but
            # force the enclosing gap onto the labelled endpoint bridge.
            unambiguous = False
            continue
        current.quantity += incoming.quantity
        current.market_value = (
            current.market_value + incoming.market_value
            if current.market_value is not None and incoming.market_value is not None
            else None
        )
        if current.quantity == ZERO:
            del result[symbol]
    return result, unambiguous


def _compatible_holdings(left: _Holding, right: _Holding) -> bool:
    if left.asset_type != right.asset_type or left.multiplier != right.multiplier:
        return False
    for left_value, right_value in (
        (left.underlying_symbol, right.underlying_symbol),
        (left.option_side, right.option_side),
        (left.expiration_date, right.expiration_date),
        (left.strike, right.strike),
        (left.is_non_standard, right.is_non_standard),
    ):
        if left_value is not None and right_value is not None and left_value != right_value:
            return False
    return True


def _holdings_match_right_anchor(
    holdings: Mapping[str, _Holding],
    right_positions: Sequence[Mapping[str, Any]],
) -> bool:
    expected: dict[str, tuple[str, Decimal, Decimal | None, bool | None]] = {}
    for row in right_positions:
        symbol = _symbol(row.get("symbol"))
        quantity = _decimal(row.get("net_quantity"))
        if not symbol or quantity == ZERO:
            continue
        asset_type = _asset_type(row.get("asset_type"))
        explicit_multiplier = (
            _optional_decimal(row.get("contract_multiplier"))
            if row.get("contract_multiplier") is not None
            else _optional_decimal(row.get("multiplier"))
        )
        standardness = optional_bool(row.get("is_non_standard"))
        current = expected.get(symbol)
        if current is not None and current[0] != asset_type:
            return False
        if (
            current is not None
            and current[2] is not None
            and explicit_multiplier is not None
            and current[2] != explicit_multiplier
        ):
            return False
        if (
            current is not None
            and current[3] is not None
            and standardness is not None
            and current[3] != standardness
        ):
            return False
        expected[symbol] = (
            asset_type,
            quantity + (current[1] if current is not None else ZERO),
            explicit_multiplier
            if explicit_multiplier is not None
            else (current[2] if current is not None else None),
            standardness
            if standardness is not None
            else (current[3] if current is not None else None),
        )
    expected = {symbol: value for symbol, value in expected.items() if value[1] != ZERO}
    if set(holdings) != set(expected):
        return False
    for symbol, holding in holdings.items():
        asset_type, quantity, multiplier, standardness = expected[symbol]
        if holding.asset_type != asset_type or holding.quantity != quantity:
            return False
        if asset_type == "option" and multiplier is not None and holding.multiplier != multiplier:
            return False
        if (
            asset_type == "option"
            and standardness is not None
            and holding.is_non_standard != standardness
        ):
            return False
    return True


def _holding_from_row(
    row: Mapping[str, Any],
    *,
    quantity: Decimal,
    multiplier: Decimal | None = None,
) -> _Holding:
    asset_type = _asset_type(row.get("asset_type"))
    return _Holding(
        symbol=_symbol(row.get("symbol")),
        asset_type=asset_type,
        quantity=quantity,
        multiplier=multiplier
        if multiplier is not None
        else _multiplier(row, asset_type=asset_type),
        market_value=_optional_decimal(row.get("market_value")),
        underlying_symbol=_symbol(row.get("underlying_symbol")) or None,
        option_side=option_side(row.get("option_side") or row.get("option_type")),
        expiration_date=_as_date(row.get("expiration_date")),
        strike=_optional_decimal(row.get("strike")),
        is_non_standard=optional_bool(row.get("is_non_standard")),
    )


def _execution_order_key(row: Mapping[str, Any]) -> str:
    external_key = str(row.get("external_key") or "").strip()
    if external_key:
        return external_key
    return "|".join(
        (
            _symbol(row.get("symbol")),
            _token(row.get("side")),
            str(_decimal(row.get("quantity"))),
            str(_decimal(row.get("price"))),
            str(_optional_decimal(row.get("net_cash")) or ""),
        )
    )


def _anchor_marks(
    left: Sequence[Mapping[str, Any]],
    right: Sequence[Mapping[str, Any]],
    left_day: date,
    right_day: date,
) -> dict[str, tuple[tuple[date, Decimal], ...]]:
    marks: dict[str, list[tuple[date, Decimal]]] = defaultdict(list)
    for day, rows in ((left_day, left), (right_day, right)):
        for row in rows:
            quantity = _decimal(row.get("net_quantity"))
            value = _optional_decimal(row.get("market_value"))
            if quantity == ZERO or value is None:
                continue
            asset_type = _asset_type(row.get("asset_type"))
            multiplier = _multiplier(row, asset_type=asset_type)
            mark = abs(value / quantity / multiplier)
            if asset_type != "option" and mark <= ZERO:
                continue
            marks[_symbol(row.get("symbol"))].append((day, mark))
    return {symbol: tuple(values) for symbol, values in marks.items()}


def _execution_marks(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[tuple[date, Decimal], ...]]:
    """Use the final execution price on a session as an estimated mark source.

    Schwab does not always return historical option bars for a contract that was
    opened and closed between two account snapshots.  The broker execution is
    still an observed transaction price.  It is eligible only as an estimated
    fallback; an actual daily bar or account-anchor mark remains authoritative.
    """

    latest: dict[tuple[str, date], tuple[datetime, Decimal, Decimal]] = {}
    for row in rows:
        symbol = _symbol(row.get("symbol"))
        occurred_at = _activity_timestamp(row.get("occurred_at"))
        price = _optional_decimal(row.get("price"))
        asset_type = _asset_type(row.get("asset_type"))
        if (
            not symbol
            or occurred_at is None
            or price is None
            or price < ZERO
            or (asset_type != "option" and price <= ZERO)
        ):
            continue
        key = (symbol, market_date(occurred_at))
        weight = abs(_decimal(row.get("quantity"))) or ONE
        current = latest.get(key)
        if current is None or occurred_at > current[0]:
            latest[key] = (occurred_at, price * weight, weight)
        elif occurred_at == current[0]:
            latest[key] = (
                occurred_at,
                current[1] + price * weight,
                current[2] + weight,
            )
    grouped: defaultdict[str, list[tuple[date, Decimal]]] = defaultdict(list)
    for (symbol, day), (_occurred_at, total, weight) in latest.items():
        grouped[symbol].append((day, total / weight))
    return {symbol: tuple(sorted(values)) for symbol, values in grouped.items()}


def _merge_marks(
    *sources: Mapping[str, tuple[tuple[date, Decimal], ...]],
) -> dict[str, tuple[tuple[date, Decimal], ...]]:
    merged: defaultdict[str, dict[date, Decimal]] = defaultdict(dict)
    for source in sources:
        for symbol, observations in source.items():
            for day, mark in observations:
                merged[symbol][day] = mark
    return {symbol: tuple(sorted(observations.items())) for symbol, observations in merged.items()}


def _bar_index(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, date], Decimal]:
    return {
        (_symbol(row.get("symbol")), row["trade_date"]): _decimal(row.get("close"))
        for row in rows
        if isinstance(row.get("trade_date"), date) and row.get("close") is not None
    }


def _account_rows(
    rows: Sequence[Mapping[str, Any]],
    account: str,
    *,
    include_unscoped: bool,
) -> tuple[Mapping[str, Any], ...]:
    return tuple(
        row for row in rows if _account(row) == account or (include_unscoped and _is_unscoped(row))
    )


def _has_unscoped_activity(
    rows: Sequence[Mapping[str, Any]],
    *,
    after: datetime,
    through: datetime,
) -> bool:
    return any(
        _is_unscoped(row)
        and (occurred_at := _activity_timestamp(row.get("occurred_at"))) is not None
        and after < occurred_at <= through
        for row in rows
    )


def _is_unscoped(row: Mapping[str, Any]) -> bool:
    return (
        not str(row.get("account_id") or "").strip()
        and not str(row.get("account_mask") or "").strip()
    )


def _delivery_side(event_type: str | None, option_side_value: object) -> str | None:
    side = option_side(option_side_value)
    if event_type not in {"assignment", "exercise"} or side is None:
        return None
    return {
        ("assignment", "call"): "sell",
        ("assignment", "put"): "buy",
        ("exercise", "call"): "buy",
        ("exercise", "put"): "sell",
    }.get((event_type, side))


def _delivery_is_incomplete(event: Mapping[str, Any]) -> bool:
    details = event.get("details")
    if isinstance(details, Mapping) and details.get("delivery_ambiguous"):
        return True
    event_type = lifecycle_event_type(event.get("event_type"))
    return (
        delivered_share_quantity(event) <= ZERO
        or not _symbol(event.get("stock_symbol") or event.get("underlying_symbol"))
        or _delivery_side(event_type, event.get("option_side")) is None
        or (event.get("cash_amount") is None and event.get("strike") is None)
    )


def _incomplete_delivery_in_window(
    event: Mapping[str, Any], *, after: datetime, through: datetime
) -> bool:
    occurred_at = _activity_timestamp(event.get("occurred_at"))
    return (
        occurred_at is not None
        and after < occurred_at <= through
        and lifecycle_event_type(event.get("event_type")) in {"assignment", "exercise"}
        and _delivery_is_incomplete(event)
    )


def _multiplier(row: Mapping[str, Any], *, asset_type: str) -> Decimal:
    if asset_type != "option":
        return ONE
    return contract_multiplier(row)


def _execution_multiplier(
    row: Mapping[str, Any],
    *,
    asset_type: str,
    holding: _Holding | None,
) -> Decimal | None:
    if asset_type == "equity":
        return ONE
    if asset_type != "option":
        return None
    raw = row.get("contract_multiplier")
    if raw is None:
        raw = row.get("multiplier")
    parsed = _optional_decimal(raw)
    explicit = abs(parsed) if parsed is not None else None
    if explicit is not None and explicit <= ZERO:
        return None
    if holding is not None:
        if holding.asset_type != "option":
            return None
        if explicit is not None and explicit != holding.multiplier:
            return None
        row_standardness = optional_bool(row.get("is_non_standard"))
        if (
            row_standardness is not None
            and holding.is_non_standard is not None
            and row_standardness != holding.is_non_standard
        ):
            return None
        return explicit if explicit is not None else holding.multiplier
    if explicit is not None:
        return explicit
    return HUNDRED if optional_bool(row.get("is_non_standard")) is False else None


def _asset_type(value: object) -> str:
    normalized = _token(value)
    if normalized in {"equity", "etf", "stock"}:
        return "equity"
    return "option" if normalized == "option" else normalized


def _account(row: Mapping[str, Any]) -> str:
    return str(row.get("account_id") or row.get("account_mask") or "ACCOUNT").strip().casefold()


def _symbol(value: object) -> str:
    return "".join(str(value or "").upper().split())


def _token(value: object) -> str:
    return str(value or "").strip().casefold().split(".")[-1]


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None
    return None


def _timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    return datetime.min.replace(tzinfo=UTC)


def _market_close(day: date) -> datetime:
    return datetime.combine(day, time(16), tzinfo=MARKET_TIME_ZONE)


def _activity_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None and value.time() == time.min:
            # SQLite strips offsets. Date-only Schwab activity is intentionally
            # normalized to midnight ET by the mapper, so restore that semantic
            # instead of shifting it onto the prior market date as midnight UTC.
            return value.replace(tzinfo=MARKET_TIME_ZONE)
        return _timestamp(value)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=MARKET_TIME_ZONE)
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=MARKET_TIME_ZONE if parsed.time() == time.min else UTC)
    return parsed


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _decimal(value: object) -> Decimal:
    return ZERO if value is None else Decimal(str(value))
