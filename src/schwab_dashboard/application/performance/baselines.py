from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.market_time import market_date
from schwab_dashboard.application.performance.flows import movement_date
from schwab_dashboard.application.performance.models import ComparisonSeries, ReturnPoint

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def build_static_share_baseline(
    *,
    position_history: Sequence[dict[str, Any]],
    daily_bars: Sequence[dict[str, Any]],
    cash_movements: Sequence[dict[str, Any]],
    actual_points: Sequence[ReturnPoint],
) -> ComparisonSeries:
    """Value the earliest observed stock inventory without subsequent trading.

    The counterfactual starts with the same net liquidation value. Everything not
    represented by starting stock lots becomes a fixed cash residual. That makes
    the comparison portfolio-sized without pretending an old option liability
    continued to exist.
    """
    if not actual_points or not position_history:
        return _unavailable("No matched historical position snapshot is available.")
    end = actual_points[-1].date
    snapshots = _snapshots_by_observation(position_history)
    eligible = [item for item in snapshots if item[0] <= end]
    if not eligible:
        return _unavailable("Position history starts after the available valuation window.")
    coverage_start = actual_points[0].date
    at_or_before_coverage = [item for item in eligible if item[0] <= coverage_start]
    # Freeze the inventory actually present when the return window begins. An
    # older snapshot may describe a materially different book after later buys,
    # assignments, or transfers.
    start_day, rows = (
        at_or_before_coverage[-1] if at_or_before_coverage else eligible[0]
    )
    quantities = _starting_stock_quantities(rows)
    if not quantities:
        return _unavailable("The first matched position snapshot has no stock inventory.")
    actual_start = next((point for point in actual_points if point.date >= start_day), None)
    if actual_start is None:
        return _unavailable("No net-liquidation value matches the starting stock snapshot.")
    series = _price_matrix(daily_bars, quantities, start=actual_start.date, end=end)
    if not series:
        return _unavailable("Daily close history does not cover every starting stock holding.")
    start_value = series[0][1]
    cash_residual = actual_start.value - start_value
    points: list[ReturnPoint] = []
    previous: Decimal | None = None
    for day, stock_value in series:
        dividends = _dividends_through(cash_movements, quantities, actual_start.date, day)
        value = stock_value + cash_residual + dividends
        daily_return = (value - previous) / previous * HUNDRED if previous else None
        cumulative = (
            (value - actual_start.value) / actual_start.value * HUNDRED
            if actual_start.value
            else None
        )
        points.append(
            ReturnPoint(
                date=day,
                value=value,
                external_flow=ZERO,
                daily_return_percent=daily_return,
                cumulative_return_percent=cumulative,
                quality="derived_price_only",
            )
        )
        previous = value
    final_return = points[-1].cumulative_return_percent if points else None
    return ComparisonSeries(
        key="shares_without_options",
        label="Starting shares, no options",
        status="derived" if final_return is not None else "waiting",
        return_percent=final_return,
        method_note=(
            "Earliest observed stock lots held unchanged; residual net liquidation stays cash. "
            "Observed cash dividends are added. No later stock trades or options are replayed."
        ),
        points=tuple(points),
    )


def build_market_price_reference(
    *,
    daily_bars: Sequence[dict[str, Any]],
    actual_points: Sequence[ReturnPoint],
    symbol: str = "SPY",
) -> ComparisonSeries:
    if not actual_points:
        return _market_unavailable(symbol)
    rows = sorted(
        (
            (row["trade_date"], Decimal(str(row["close"])))
            for row in daily_bars
            if str(row.get("symbol") or "").upper() == symbol
            and actual_points[0].date <= row["trade_date"] <= actual_points[-1].date
        ),
        key=lambda item: item[0],
    )
    if len(rows) < 2 or rows[0][1] == ZERO:
        return _market_unavailable(symbol)
    start_gap = rows[0][0] - actual_points[0].date
    end_gap = actual_points[-1].date - rows[-1][0]
    # Weekend/holiday offsets are expected, but a price series starting or
    # ending materially inside the account window is not a valid benchmark.
    if start_gap > timedelta(days=4) or end_gap > timedelta(days=4):
        return _market_unavailable(symbol)
    first = rows[0][1]
    previous: Decimal | None = None
    built: list[ReturnPoint] = []
    previous = None
    for day, value in rows:
        built.append(
            ReturnPoint(
                date=day,
                value=value,
                external_flow=ZERO,
                daily_return_percent=(
                    (value - previous) / previous * HUNDRED if previous else None
                ),
                cumulative_return_percent=(value - first) / first * HUNDRED,
                quality="price_only",
            )
        )
        previous = value
    return ComparisonSeries(
        key="market_reference",
        label=f"{symbol} price",
        status="price_only",
        return_percent=built[-1].cumulative_return_percent,
        method_note=f"{symbol} close-to-close price return. Dividends are not included.",
        points=tuple(built),
    )


def _snapshots_by_observation(
    rows: Sequence[dict[str, Any]],
) -> list[tuple[date, tuple[dict[str, Any], ...]]]:
    grouped: dict[tuple[str, date], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        observed = row.get("observed_at")
        if observed is not None:
            grouped[(str(row.get("sync_run_id") or observed), market_date(observed))].append(row)
    return sorted(
        ((day, tuple(items)) for (_, day), items in grouped.items()),
        key=lambda item: item[0],
    )


def _starting_stock_quantities(rows: Sequence[dict[str, Any]]) -> dict[str, Decimal]:
    result: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for row in rows:
        if str(row.get("asset_type") or "").upper() == "OPTION":
            continue
        symbol = str(row.get("symbol") or "").upper()
        if symbol:
            result[symbol] += Decimal(str(row.get("net_quantity") or "0"))
    return {symbol: quantity for symbol, quantity in result.items() if quantity != ZERO}


def _price_matrix(
    rows: Sequence[dict[str, Any]],
    quantities: dict[str, Decimal],
    *,
    start: date,
    end: date,
) -> list[tuple[date, Decimal]]:
    by_day: dict[date, dict[str, Decimal]] = defaultdict(dict)
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        day = row.get("trade_date")
        if symbol in quantities and isinstance(day, date) and start <= day <= end:
            by_day[day][symbol] = Decimal(str(row.get("close") or "0"))
    return [
        (
            day,
            sum((quantities[symbol] * prices[symbol] for symbol in quantities), ZERO),
        )
        for day, prices in sorted(by_day.items())
        if all(symbol in prices for symbol in quantities)
    ]


def _dividends_through(
    rows: Sequence[dict[str, Any]],
    quantities: dict[str, Decimal],
    start: date,
    end: date,
) -> Decimal:
    return sum(
        (
            Decimal(str(row.get("amount") or "0"))
            for row in rows
            if str(row.get("movement_type") or "").lower() == "dividend"
            and str(row.get("symbol") or "").upper() in quantities
            and (day := movement_date(row.get("occurred_at"))) is not None
            and start <= day <= end
        ),
        ZERO,
    )


def _unavailable(note: str) -> ComparisonSeries:
    return ComparisonSeries(
        key="shares_without_options",
        label="Starting shares, no options",
        status="not_available",
        return_percent=None,
        method_note=note,
        points=(),
    )


def _market_unavailable(symbol: str) -> ComparisonSeries:
    return ComparisonSeries(
        key="market_reference",
        label=f"{symbol} reference",
        status="not_available",
        return_percent=None,
        method_note=(
            f"No complete {symbol} daily price series is stored for this coverage window. "
            "A total-return benchmark is not invented from partial data."
        ),
        points=(),
    )
