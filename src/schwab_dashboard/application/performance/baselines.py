from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.market_time import market_date
from schwab_dashboard.application.performance.flows import external_flow_between, movement_date
from schwab_dashboard.application.performance.models import ComparisonSeries, ReturnPoint

ZERO = Decimal("0")
HUNDRED = Decimal("100")
# Brokers accrue margin interest on a 360-day year, Schwab included, so a 365-day
# divisor would quietly under-bill the financed counterfactual by about 1.4%.
INTEREST_DAY_COUNT = Decimal("360")


@dataclass(frozen=True, slots=True)
class _FrozenStart:
    """The single anchor both counterfactuals are built from.

    Every do-nothing comparison has to begin on the same session, at the same
    dollar exposure, with the same cash plug. Deriving that separately per
    baseline lets the anchors drift apart the moment one symbol's bar history
    starts a day later, and two baselines measured from different days cannot be
    read against each other or against the managed book.
    """

    anchor_day: date
    exposure: Decimal
    net_liquidation: Decimal
    quantities: dict[str, Decimal]
    shorted: tuple[str, ...]
    stock_series: tuple[tuple[date, Decimal], ...]
    carried: dict[str, date]

    @property
    def cash_residual(self) -> Decimal:
        """Net liquidation the frozen stock does not account for; negative is margin."""
        return self.net_liquidation - self.exposure


def _frozen_start(
    *,
    position_history: Sequence[dict[str, Any]],
    daily_bars: Sequence[dict[str, Any]],
    actual_points: Sequence[ReturnPoint],
) -> _FrozenStart | str:
    """Resolve the shared anchor, or explain in prose why none exists."""

    if not actual_points or not position_history:
        return "No matched historical position snapshot is available."
    end = actual_points[-1].date
    eligible = [item for item in _snapshots_by_observation(position_history) if item[0] <= end]
    if not eligible:
        return "Position history starts after the available valuation window."
    coverage_start = actual_points[0].date
    at_or_before_coverage = [item for item in eligible if item[0] <= coverage_start]
    # Freeze the inventory actually present when the return window begins. An
    # older snapshot may describe a materially different book after later buys,
    # assignments, or transfers.
    start_day, rows = at_or_before_coverage[-1] if at_or_before_coverage else eligible[0]
    quantities, shorted = _starting_stock_quantities(rows)
    if not quantities:
        return "The first matched position snapshot has no long stock inventory."
    actual_start = next((point for point in actual_points if point.date >= start_day), None)
    if actual_start is None:
        return "No net-liquidation value matches the starting stock snapshot."
    series, carried = _price_matrix(daily_bars, quantities, start=actual_start.date, end=end)
    if not series:
        return "Daily close history does not cover every starting stock holding."
    anchor_day, exposure = series[0]
    return _FrozenStart(
        anchor_day=anchor_day,
        exposure=exposure,
        net_liquidation=actual_start.value,
        quantities=quantities,
        shorted=shorted,
        stock_series=tuple(series),
        carried=carried,
    )


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
    start = _frozen_start(
        position_history=position_history,
        daily_bars=daily_bars,
        actual_points=actual_points,
    )
    if isinstance(start, str):
        return _unavailable(start)
    anchor_day = start.anchor_day
    quantities, shorted, carried = start.quantities, start.shorted, start.carried
    cash_residual = start.cash_residual
    points: list[ReturnPoint] = []
    previous: Decimal | None = None
    cumulative_factor = Decimal("1")
    flows_to_date = ZERO
    previous_day = anchor_day
    for day, stock_value in start.stock_series:
        # Owner transfers must land in the counterfactual as idle cash by the
        # valuation that first covers them, and the chain must be time-weighted
        # exactly like the managed series. Otherwise a deposit grows only the
        # managed book's denominator for the rest of the window, and the tile
        # reports the owner's own funding decision as management
        # underperformance. The span, not the single day, is what must be swept:
        # a transfer settling over a weekend belongs to the next session.
        flow = _flow_into(cash_movements, after=previous_day, through=day, anchor=anchor_day)
        flows_to_date += flow
        dividends = _dividends_through(cash_movements, quantities, anchor_day, day)
        value = stock_value + cash_residual + flows_to_date + dividends
        daily_return: Decimal | None = None
        if previous:
            daily_return = (value - previous - flow) / previous * HUNDRED
            cumulative_factor *= Decimal("1") + daily_return / HUNDRED
        points.append(
            ReturnPoint(
                date=day,
                value=value,
                external_flow=flow,
                daily_return_percent=daily_return,
                cumulative_return_percent=(cumulative_factor - Decimal("1")) * HUNDRED,
                quality="derived_price_only",
            )
        )
        previous = value
        previous_day = day
    final_return = points[-1].cumulative_return_percent if points else None
    note = (
        "Earliest observed long stock lots held unchanged; residual net liquidation stays cash. "
        "Owner transfers arrive as idle cash on the day they settle and returns are chained "
        "time-weighted, matching the managed book. Observed cash dividends are added. "
        "No later stock trades or options are replayed."
    )
    if shorted:
        note = (
            f"{note} Short stock ({', '.join(shorted)}) is excluded because a passive hold "
            "cannot carry a borrow; its opening value stays in the cash residual."
        )
    if carried:
        held_flat = ", ".join(
            f"{symbol} at its {day:%b %d} close" for symbol, day in sorted(carried.items())
        )
        note = f"{note} No newer daily bar exists for {held_flat}, so it is held flat from there."
    status = "waiting" if final_return is None else "carried_forward" if carried else "derived"
    return ComparisonSeries(
        key="shares_without_options",
        label="Starting shares, no options",
        status=status,
        return_percent=final_return,
        method_note=note,
        points=tuple(points),
    )


def build_levered_market_baseline(
    *,
    position_history: Sequence[dict[str, Any]],
    daily_bars: Sequence[dict[str, Any]],
    cash_movements: Sequence[dict[str, Any]],
    actual_points: Sequence[ReturnPoint],
    annual_interest_rate_percent: Decimal,
    symbol: str = "SPY",
) -> ComparisonSeries:
    """The index bought at the book's own starting exposure, financed the same way.

    An unlevered index line is not a fair read on a margined account. Gross
    equity exposure well above net liquidation wins against a cash index in any
    rising tape and loses far worse in a falling one, with no decision of the
    owner's involved either way, so the plain price tile silently reports
    borrowing as skill.

    This holds the exposure constant in shares rather than resetting to a target
    leverage each morning. A real margin position is never rebalanced daily, and
    imposing that would introduce volatility decay the account never suffered.
    Leverage is therefore free to drift exactly as it did in the book, whether
    from profit and loss or from a deposit landing mid-window.
    """

    start = _frozen_start(
        position_history=position_history,
        daily_bars=daily_bars,
        actual_points=actual_points,
    )
    if isinstance(start, str):
        return _levered_unavailable(symbol, start)
    closes = {
        row["trade_date"]: Decimal(str(row.get("close") or "0"))
        for row in daily_bars
        if str(row.get("symbol") or "").upper() == symbol
        and isinstance(row.get("trade_date"), date)
    }
    anchor_day = start.anchor_day
    anchor_close = closes.get(anchor_day)
    if anchor_close is None or anchor_close <= ZERO:
        return _levered_unavailable(
            symbol,
            f"No {symbol} close is stored for {anchor_day:%b %d, %Y}, the session both "
            "counterfactuals are anchored to.",
        )
    last_stock_day = start.stock_series[-1][0]
    sessions = sorted(
        day for day in closes if anchor_day <= day <= last_stock_day and closes[day] > ZERO
    )
    shares = start.exposure / anchor_close
    # Negative cash is the margin debit that funds exposure above net liquidation.
    cash = start.cash_residual
    financed = cash < ZERO
    points: list[ReturnPoint] = []
    previous: Decimal | None = None
    cumulative_factor = Decimal("1")
    previous_day = anchor_day
    interest_paid = ZERO
    for day in sessions:
        elapsed = (day - previous_day).days
        if cash < ZERO and elapsed > 0:
            charge = (
                -cash
                * annual_interest_rate_percent
                / HUNDRED
                * Decimal(elapsed)
                / INTEREST_DAY_COUNT
            )
            cash -= charge
            interest_paid += charge
        flow = _flow_into(cash_movements, after=previous_day, through=day, anchor=anchor_day)
        cash += flow
        value = shares * closes[day] + cash
        daily_return: Decimal | None = None
        if previous:
            daily_return = (value - previous - flow) / previous * HUNDRED
            cumulative_factor *= Decimal("1") + daily_return / HUNDRED
        points.append(
            ReturnPoint(
                date=day,
                value=value,
                external_flow=flow,
                daily_return_percent=daily_return,
                cumulative_return_percent=(cumulative_factor - Decimal("1")) * HUNDRED,
                quality="derived_levered",
            )
        )
        previous = value
        previous_day = day
    if len(points) < 2:
        return _levered_unavailable(
            symbol,
            f"Fewer than two {symbol} closes fall inside the anchored window.",
        )
    leverage = start.exposure / start.net_liquidation if start.net_liquidation else ZERO
    note = (
        f"{symbol} bought on {anchor_day:%b %d, %Y} at the book's own starting equity exposure "
        f"of {start.exposure:,.0f} against {start.net_liquidation:,.0f} net liquidation, "
        f"or {leverage:.2f}x. Share count never changes, so leverage drifts with profit and "
        "loss and with deposits exactly as it did in the account, rather than being reset daily. "
        "Owner transfers arrive as idle cash and returns are chained time-weighted, matching "
        "the managed book."
    )
    if financed:
        note = (
            f"{note} The borrowed portion is charged {annual_interest_rate_percent:.2f}% annually "
            f"on a 360-day basis, {interest_paid:,.0f} so far; without that cost the reference "
            "would be borrowing for free and would read as an unfairly hard bar. Set "
            "SCHWAB_DASHBOARD_MARGIN_INTEREST_RATE_PERCENT to the account's real rate."
        )
    else:
        note = f"{note} Exposure never exceeded net liquidation, so no financing is charged."
    return ComparisonSeries(
        key="levered_market_reference",
        label=f"{symbol} at your exposure",
        status="derived_levered",
        return_percent=points[-1].cumulative_return_percent,
        method_note=note,
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


def _starting_stock_quantities(
    rows: Sequence[dict[str, Any]],
) -> tuple[dict[str, Decimal], tuple[str, ...]]:
    """Freeze the long stock lots only, and report any short that was dropped.

    A short sale is not something a do-nothing baseline can hold: it carries a
    borrow, a margin requirement, and an eventual forced buy-in, so pretending
    one stayed open for the life of the window charges the managed book for
    closing a tactical trade that was never a long-term holding. Net
    liquidation is preserved regardless, because the residual cash plug absorbs
    whatever the excluded short was worth on day one.
    """

    result: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for row in rows:
        if str(row.get("asset_type") or "").upper() == "OPTION":
            continue
        symbol = str(row.get("symbol") or "").upper()
        if symbol:
            result[symbol] += Decimal(str(row.get("net_quantity") or "0"))
    held = {symbol: quantity for symbol, quantity in result.items() if quantity > ZERO}
    shorted = tuple(sorted(symbol for symbol, quantity in result.items() if quantity < ZERO))
    return held, shorted


def _price_matrix(
    rows: Sequence[dict[str, Any]],
    quantities: dict[str, Decimal],
    *,
    start: date,
    end: date,
) -> tuple[list[tuple[date, Decimal]], dict[str, date]]:
    """Value the frozen lots each day, holding a lapsed symbol at its last close.

    A position closed early in the window stops receiving fresh bars, and
    requiring every frozen symbol to price on the same day let one lapsed
    ticker truncate the entire counterfactual — discarding sessions the
    remaining holdings priced perfectly well. Carrying the last observed close
    keeps the comparison running; the caller reports which symbols were carried
    so a held-flat price is never mistaken for an observed one.
    """

    closes: dict[str, dict[date, Decimal]] = defaultdict(dict)
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        day = row.get("trade_date")
        if symbol in quantities and isinstance(day, date) and day <= end:
            closes[symbol][day] = Decimal(str(row.get("close") or "0"))

    grid = sorted({day for prices in closes.values() for day in prices if start <= day <= end})
    series: list[tuple[date, Decimal]] = []
    carried: dict[str, date] = {}
    for day in grid:
        priced: dict[str, Decimal] = {}
        held_flat: dict[str, date] = {}
        for symbol in quantities:
            observed = [known for known in closes[symbol] if known <= day]
            if not observed:
                break
            latest = max(observed)
            priced[symbol] = closes[symbol][latest]
            if latest != day:
                held_flat[symbol] = latest
        # A day before some symbol's first bar cannot be valued at all, and its
        # partial pricing must not be reported as a carry the series relied on.
        if len(priced) != len(quantities):
            continue
        carried.update(held_flat)
        series.append(
            (day, sum((quantities[symbol] * priced[symbol] for symbol in quantities), ZERO))
        )
    return series, carried


def _flow_into(
    cash_movements: Sequence[dict[str, Any]],
    *,
    after: date,
    through: date,
    anchor: date,
) -> Decimal:
    """Owner transfers belonging to one valuation, zero on the anchor itself.

    Whatever settled on or before the anchor is already inside the starting net
    liquidation, so counting it again would double the opening capital.
    """
    if through <= anchor:
        return ZERO
    return external_flow_between(cash_movements, after=after, through=through)


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


def _levered_unavailable(symbol: str, note: str) -> ComparisonSeries:
    return ComparisonSeries(
        key="levered_market_reference",
        label=f"{symbol} at your exposure",
        status="not_available",
        return_percent=None,
        method_note=(
            f"{note} A leverage-matched {symbol} line is left blank rather than "
            "approximated from a different starting point."
        ),
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
