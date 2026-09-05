"""A complete fictional account ledger for demonstrating the production return spine.

The stock closes and share prints are the same frozen fixtures as the demo tape.
Option marks, account balances, the owner deposit and SPY path are illustrative.
This is neither a backtest nor the author's account performance.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from math import sin
from typing import Any

from schwab_dashboard.application.dashboard.covered_calls import CallSaleRecord
from schwab_dashboard.application.dashboard.models import PositionSummary
from schwab_dashboard.application.performance.models import PerformanceComparison
from schwab_dashboard.application.performance.periods import PerformancePeriod
from schwab_dashboard.application.performance.projection import build_performance_comparison
from schwab_dashboard.application.performance.sessions import build_market_calendar
from schwab_dashboard.infrastructure.demo.fixtures.cash_events import build_dividend_cash_events
from schwab_dashboard.infrastructure.demo.fixtures.daily_prices import DAILY_CLOSES
from schwab_dashboard.infrastructure.demo.fixtures.share_trades import SHARE_TRADES

D = Decimal
ZERO = D("0")
CENT = D("0.01")
ACCOUNT = "demo-brokerage"
DEMO_PROVENANCE = (
    "FICTIONAL DEMO: illustrative account inventory, option marks, owner cash and SPY path; "
    "stock closes reuse the frozen demo tape. These are not live results or a backtest. "
    "Supplemental share round trips keep calls covered. A $5,000 owner deposit and "
    "$50,000 withdrawal of starting cash are excluded from returns when inside the window. "
    "Observed/derived quality labels describe completeness within this fictional scenario."
)


@dataclass(frozen=True, slots=True)
class DemoPerformanceHistory:
    balance_history: tuple[dict[str, Any], ...]
    position_history: tuple[dict[str, Any], ...]
    daily_bars: tuple[dict[str, Any], ...]
    cash_movements: tuple[dict[str, Any], ...]
    executions: tuple[dict[str, Any], ...]
    lifecycle_events: tuple[dict[str, Any], ...]


def build_demo_performance_comparison(
    *,
    positions: Sequence[PositionSummary],
    cash_value: Decimal,
    call_history: Sequence[CallSaleRecord],
    as_of: date,
    period: PerformancePeriod = PerformancePeriod.ALL,
    put_executions: Sequence[dict[str, Any]] = (),
) -> PerformanceComparison:
    history = build_demo_performance_history(
        positions=positions,
        cash_value=cash_value,
        call_history=call_history,
        as_of=as_of,
        put_executions=put_executions,
    )
    starts_on = period.starts_on(through=as_of)
    balances = tuple(
        row
        for row in history.balance_history
        if starts_on is None or row["observed_at"].date() >= starts_on
    )
    comparison = build_performance_comparison(
        balance_history=balances,
        cash_movements=history.cash_movements,
        position_history=history.position_history,
        daily_bars=history.daily_bars,
        executions=history.executions,
        lifecycle_events=history.lifecycle_events,
    )

    # Keep the production calculations and status vocabulary, but never describe
    # illustrative valuations as broker evidence in standalone JSON or tooltips.
    def described(value: Any) -> Any:
        note = value.method_note.replace("broker", "fictional demo").replace(
            "latest published close", "last fixture close"
        )
        return replace(value, method_note=f"{DEMO_PROVENANCE} {note}")

    spine = comparison.spine
    return replace(
        comparison,
        actual=described(comparison.actual),
        shares_without_options=described(comparison.shares_without_options),
        option_overlay=described(comparison.option_overlay),
        market_reference=described(comparison.market_reference),
        levered_market_reference=described(comparison.levered_market_reference),
        matched=described(comparison.matched),
        spine=replace(
            spine,
            management_edge=described(spine.management_edge),
            risk=described(spine.risk),
            option_economics=described(spine.option_economics),
            capital_efficiency=replace(
                described(spine.capital_efficiency),
                method_note=(
                    f"{DEMO_PROVENANCE} Maintenance is an illustrative 30% stock reserve plus "
                    "full put strike collateral. Available cash subtracts that collateral; "
                    "buying power is twice that remainder. These are display fixtures, not "
                    "Schwab margin calculations. Option cash on average capital is a cash "
                    "ratio, not a portfolio return."
                ),
            ),
            assignment_impact=described(spine.assignment_impact),
            benchmark_policy=tuple(described(item) for item in spine.benchmark_policy),
        ),
        warnings=(DEMO_PROVENANCE, *comparison.warnings),
    )


def build_demo_performance_history(
    *,
    positions: Sequence[PositionSummary],
    cash_value: Decimal,
    call_history: Sequence[CallSaleRecord],
    as_of: date,
    put_executions: Sequence[dict[str, Any]] = (),
) -> DemoPerformanceHistory:
    """Replay fixture cash and quantities, anchored exactly to the displayed book."""
    equities = {item.symbol: item for item in positions if item.asset_type == "EQUITY"}
    current_options = {item.symbol: item for item in positions if item.asset_type == "OPTION"}
    bars: list[dict[str, Any]] = [
        {
            "symbol": symbol,
            "trade_date": date(2026, int(label[:2]), int(label[3:])),
            "close": D(close),
            "source": "demo_frozen_stock_tape",
        }
        for symbol in equities
        for label, close in DAILY_CLOSES[symbol]
        if date(2026, int(label[:2]), int(label[3:])) <= as_of
    ]
    calendar = build_market_calendar(())
    sessions = sorted({row["trade_date"] for row in bars if calendar.is_session(row["trade_date"])})
    if len(sessions) < 2 or sessions[-1] != as_of:
        raise ValueError("Demo performance requires a closing date covered by the frozen tape.")
    closes = {(row["symbol"], row["trade_date"]): row["close"] for row in bars}
    for symbol, item in equities.items():
        if item.market_value is None or item.quantity <= ZERO:
            raise ValueError("Demo stock positions need a positive quantity and complete value.")
        closes[symbol, as_of] = item.market_value / item.quantity
    for row in bars:
        row["close"] = closes[row["symbol"], row["trade_date"]]
    for index, day in enumerate(sessions):
        progress = D(index) / D(len(sessions) - 1)
        # Explicitly synthetic; modest positive drift includes a visible selloff.
        wave = D(str(sin(float(progress) * 11))) * D("0.014")
        drawdown = max(ZERO, D("1") - abs(progress - D("0.6")) / D("0.16")) * D("0.035")
        bars.append(
            {
                "symbol": "SPY",
                "trade_date": day,
                "close": (D("600") * (D("1") + progress * D("0.045") + wave - drawdown)).quantize(
                    CENT
                ),
                "source": "fictional_demo_spy",
            }
        )

    executions, lifecycle = _option_ledger(call_history)
    executions.extend(
        {
            **row,
            "account_id": ACCOUNT,
            "account_mask": "...4831",
            "asset_type": "OPTION",
            "position_effect": "OPEN",
            "option_side": "PUT",
            "side": "SELL",
        }
        for row in put_executions
    )
    for symbol, trades in SHARE_TRADES.items():
        if symbol not in equities:
            continue
        for trade in trades:
            if trade.traded_on > as_of:
                continue
            executions.append(
                {
                    **_identity(
                        f"shares-{symbol}-{trade.traded_on}-{trade.action}", trade.traded_on
                    ),
                    "symbol": symbol,
                    "asset_type": "EQUITY",
                    "side": trade.action,
                    "quantity": D(trade.shares),
                    "price": trade.price,
                    "fees": ZERO,
                    "net_cash": D(trade.shares)
                    * trade.price
                    * (D("-1") if trade.action == "buy" else D("1")),
                }
            )
    executions = [row for row in executions if row["occurred_at"].date() <= as_of]
    lifecycle = [row for row in lifecycle if row["occurred_at"].date() <= as_of]
    movements = [
        {
            **_identity(event.event_id, event.occurred_on),
            "movement_type": "dividend",
            "symbol": event.symbol,
            "amount": event.amount,
        }
        for event in build_dividend_cash_events()
        if event.occurred_on <= as_of
    ]
    movements.append(
        {
            **_identity("illustrative-owner-deposit", date(2026, 6, 12)),
            "movement_type": "transfer",
            "amount": D("5000"),
        }
    )
    # The fictional starting capital includes a $50,000 cash buffer. The owner
    # later withdraws it; this is a classified external flow, not an unexplained
    # valuation plug or a return. It keeps supplemental covered stock purchases
    # funded without inventing margin borrowing or omitted interest costs.
    movements.append(
        {
            **_identity("illustrative-owner-withdrawal", date(2026, 8, 5)),
            "movement_type": "transfer",
            "amount": D("-50000"),
        }
    )
    movements = [row for row in movements if row["occurred_at"].date() <= as_of]

    cash_changes = [(row["occurred_at"].date(), D(str(row["net_cash"]))) for row in executions]
    cash_changes.extend((row["occurred_at"].date(), row["amount"]) for row in movements)
    share_changes: list[tuple[date, str, Decimal]] = [
        (
            row["occurred_at"].date(),
            row["symbol"],
            row["quantity"] * (D("1") if row["side"] == "buy" else D("-1")),
        )
        for row in executions
        if row["asset_type"] == "EQUITY"
    ]
    for row in lifecycle:
        if row["event_type"] != "assignment":
            continue
        change = (
            row["option_quantity"] * D("100") * (D("1") if row["option_side"] == "PUT" else D("-1"))
        )
        day = row["occurred_at"].date()
        share_changes.append((day, row["underlying_symbol"], change))
        cash_changes.append((day, -change * row["strike"]))
    initial_cash = cash_value - sum((amount for _, amount in cash_changes), ZERO)
    initial_shares = {
        symbol: item.quantity
        - sum((amount for _, name, amount in share_changes if name == symbol), ZERO)
        for symbol, item in equities.items()
    }
    # A size-increasing roll has a matched roll fill and an additional opening
    # fill. Merge those same-session lots only for the daily inventory marks;
    # keep their separate cash records for production campaign reconciliation.
    opening_lots: dict[tuple[str, date], dict[str, Any]] = {}
    for row in executions:
        if row["asset_type"] != "OPTION" or row["position_effect"] != "OPEN":
            continue
        key = row["symbol"], row["occurred_at"].date()
        if key not in opening_lots:
            opening_lots[key] = dict(row)
        else:
            for field in ("quantity", "gross_amount", "net_cash", "fees"):
                opening_lots[key][field] += row[field]
    option_openings = tuple(opening_lots.values())
    balances: list[dict[str, Any]] = []
    inventory: list[dict[str, Any]] = []
    for day in sessions:
        cash = initial_cash + sum((amount for when, amount in cash_changes if when <= day), ZERO)
        daily_positions: list[dict[str, Any]] = []
        for symbol in equities:
            quantity = initial_shares[symbol] + sum(
                (amount for when, name, amount in share_changes if name == symbol and when <= day),
                ZERO,
            )
            daily_positions.append(
                {
                    **_identity(symbol, day, hour=21),
                    "symbol": symbol,
                    "asset_type": "EQUITY",
                    "net_quantity": quantity,
                    "market_value": quantity * closes[symbol, day],
                }
            )
        for opening in option_openings:
            position = _option_position(
                opening, executions, lifecycle, current_options, closes, day, as_of
            )
            if position is not None:
                daily_positions.append(position)
        stock = sum(
            (row["market_value"] for row in daily_positions if row["asset_type"] == "EQUITY"), ZERO
        )
        options = sum(
            (row["market_value"] for row in daily_positions if row["asset_type"] == "OPTION"), ZERO
        )
        collateral = sum(
            (
                abs(row["net_quantity"]) * row["strike"] * D("100")
                for row in daily_positions
                if row["asset_type"] == "OPTION" and row["option_side"] == "PUT"
            ),
            ZERO,
        )
        available = max(ZERO, cash - collateral)
        balances.append(
            {
                **_identity("balance", day, hour=21),
                "liquidation_value": stock + options + cash,
                "cash_balance": cash,
                "maintenance_requirement": (stock * D("0.30") + collateral).quantize(CENT),
                "buying_power": available * D("2"),
                "available_funds": available,
                "valuation_subtype": "fictional_demo",
                "source": "fictional_demo",
            }
        )
        inventory.extend(daily_positions)
    latest = {row["symbol"]: row for row in daily_positions}
    if set(latest) != {item.symbol for item in positions} or any(
        latest[item.symbol]["net_quantity"] != item.quantity
        or latest[item.symbol]["market_value"] != item.market_value
        for item in positions
    ):
        raise ValueError(
            "Demo history does not reconcile to current positions; include every open execution."
        )
    return DemoPerformanceHistory(
        tuple(balances),
        tuple(inventory),
        tuple(bars),
        tuple(movements),
        tuple(executions),
        tuple(lifecycle),
    )


def _identity(key: str, day: date, *, hour: int = 18) -> dict[str, Any]:
    return {
        "account_id": ACCOUNT,
        "account_mask": "...4831",
        "external_key": f"demo-{key}",
        "observed_at": datetime(day.year, day.month, day.day, hour, tzinfo=UTC),
        "occurred_at": datetime(day.year, day.month, day.day, hour, tzinfo=UTC),
    }


def _option_ledger(
    records: Sequence[CallSaleRecord],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    executions: list[dict[str, Any]] = []
    lifecycle: list[dict[str, Any]] = []
    by_id = {record.record_id: record for record in records}
    successor = {record.parent_record_id: record for record in records if record.parent_record_id}
    for record in records:
        side = record.option_side.upper()
        symbol = (
            f"{record.symbol} {record.expires_on:%y%m%d}{side[0]}{int(record.strike * 1000):08d}"
        )
        common = {
            "symbol": symbol,
            "underlying_symbol": record.symbol,
            "asset_type": "OPTION",
            "option_side": side,
            "strike": record.strike,
            "expiration_date": record.expires_on,
            "quantity": D(record.contracts),
            "contract_multiplier": D("100"),
        }
        opening = {
            **_identity(f"{record.record_id}-open", record.sold_on),
            **common,
            "order_external_key": f"demo-roll-{record.parent_record_id}"
            if record.parent_record_id
            else f"demo-open-{record.record_id}",
            "side": "SELL",
            "position_effect": "OPEN",
            "price": record.premium_per_share,
            "gross_amount": record.gross_premium,
            "fees": record.fees,
            "net_cash": record.gross_premium - record.fees,
        }
        parent = by_id.get(record.parent_record_id or "")
        if parent is not None and record.contracts > parent.contracts:
            for suffix, contracts in (
                ("1-roll", parent.contracts),
                ("2-add", record.contracts - parent.contracts),
            ):
                fraction = D(contracts) / D(record.contracts)
                executions.append(
                    {
                        **opening,
                        "external_key": f"{opening['external_key']}-{suffix}",
                        "quantity": D(contracts),
                        "gross_amount": record.gross_premium * fraction,
                        "fees": record.fees * fraction,
                        "net_cash": (record.gross_premium - record.fees) * fraction,
                    }
                )
        else:
            executions.append(opening)
        if record.closed_on is None:
            continue
        if record.outcome in {"Closed", "Rolled"}:
            executions.append(
                {
                    **_identity(f"{record.record_id}-close", record.closed_on),
                    **common,
                    "order_external_key": f"demo-roll-{record.record_id}"
                    if record.record_id in successor
                    else f"demo-close-{record.record_id}",
                    "side": "BUY",
                    "position_effect": "CLOSE",
                    "gross_amount": record.buyback_cost,
                    "fees": ZERO,
                    "net_cash": -record.buyback_cost,
                }
            )
        elif record.outcome in {"Expired", "Assigned"}:
            lifecycle.append(
                {
                    **_identity(f"{record.record_id}-resolve", record.closed_on),
                    **common,
                    "event_type": "expiration" if record.outcome == "Expired" else "assignment",
                    "option_quantity": D(record.contracts),
                    "delivered_shares_per_contract": D("100"),
                }
            )
    return executions, lifecycle


def _option_position(
    opening: dict[str, Any],
    executions: Sequence[dict[str, Any]],
    lifecycle: Sequence[dict[str, Any]],
    current: dict[str, PositionSummary],
    closes: dict[tuple[str, date], Decimal],
    day: date,
    as_of: date,
) -> dict[str, Any] | None:
    sold_on = opening["occurred_at"].date()
    if sold_on > day:
        return None
    symbol = opening["symbol"]
    ending = next(
        (
            row
            for row in (*executions, *lifecycle)
            if row["symbol"] == symbol
            and (row.get("position_effect") == "CLOSE" or row.get("event_type"))
        ),
        None,
    )
    ends_on = ending["occurred_at"].date() if ending else as_of
    if ending and day >= ends_on:
        return None
    quantity = -abs(D(str(opening["quantity"])))
    multiplier = D("100")
    entry_value = D(str(opening["gross_amount"]))
    if ending is not None:
        final_liability = abs(D(str(ending.get("net_cash") or ZERO)))
    elif symbol in current and current[symbol].market_value is not None:
        final_liability = abs(current[symbol].market_value or ZERO)
    else:
        raise ValueError(f"Open demo execution has no matching current option: {symbol}")
    progress = D((day - sold_on).days) / D(max(1, (ends_on - sold_on).days))
    liability = entry_value + (final_liability - entry_value) * progress
    spot = closes[opening["underlying_symbol"], day]
    strike = D(str(opening["strike"]))
    intrinsic = max(ZERO, strike - spot if opening["option_side"] == "PUT" else spot - strike)
    liability = max(liability, intrinsic * abs(quantity) * multiplier).quantize(CENT)
    if day == as_of and symbol in current:
        if quantity != current[symbol].quantity:
            raise ValueError(f"Demo opening quantity disagrees with current position: {symbol}")
        liability = abs(current[symbol].market_value or ZERO)
    return {
        **_identity(symbol, day, hour=21),
        "symbol": symbol,
        "underlying_symbol": opening["underlying_symbol"],
        "asset_type": "OPTION",
        "option_side": opening["option_side"],
        "strike": strike,
        "net_quantity": quantity,
        "market_value": -liability,
        "short_open_profit_loss": entry_value - liability,
    }
