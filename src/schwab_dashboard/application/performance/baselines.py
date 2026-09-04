from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.market_time import MARKET_TIME_ZONE, market_date
from schwab_dashboard.application.performance.flows import (
    external_flow_between_instants,
    movement_date,
)
from schwab_dashboard.application.performance.models import ComparisonSeries, ReturnPoint
from schwab_dashboard.application.performance.share_replay import (
    apply_discretionary_equity,
    classify_forced_equity,
    live_long_quantity,
    scaled_dividend,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")
# Brokers accrue margin interest on a 360-day year, Schwab included, so a 365-day
# divisor would quietly under-bill the financed counterfactual by about 1.4%.
INTEREST_DAY_COUNT = Decimal("360")
MAX_CARRIED_MARKET_SESSIONS = 3


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
    account_id: str
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
    accounts = {
        str(row.get("account_id") or row.get("account_mask") or "").strip().casefold()
        for row in position_history
    } - {""}
    if len(accounts) > 1:
        return (
            "The shares counterfactual is unavailable for multiple accounts until "
            "account-separated lots are supported."
        )
    end = actual_points[-1].date
    eligible = [item for item in _snapshots_by_observation(position_history) if item[0] <= end]
    if not eligible:
        return "Position history starts after the available valuation window."
    coverage_start = actual_points[0].date
    at_or_before_coverage = [item for item in eligible if item[0] <= coverage_start]
    # Freeze the inventory actually present when the return window begins. An
    # older snapshot may describe a materially different book after later buys,
    # assignments, or transfers.
    if not at_or_before_coverage:
        return "Position history starts after the available valuation window."
    _start_day, rows = at_or_before_coverage[-1]
    quantities, shorted = _starting_stock_quantities(rows)
    if not quantities:
        return "The first matched position snapshot has no long stock inventory."
    actual_start = actual_points[0]
    series, carried = _price_matrix(
        daily_bars,
        quantities,
        sessions=tuple(point.date for point in actual_points),
    )
    if not series or series[0][0] != coverage_start:
        return "Daily close history does not cover every starting stock holding."
    anchor_day, exposure = series[0]
    return _FrozenStart(
        anchor_day=anchor_day,
        account_id=next(iter(accounts), ""),
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
    executions: Sequence[dict[str, Any]] = (),
    lifecycle_events: Sequence[dict[str, Any]] = (),
    annual_interest_rate_percent: Decimal = Decimal("11"),
) -> ComparisonSeries:
    """Starting long lots plus discretionary share trades, no overlay.

    Opening non-stock cash is frozen. It subsequently changes only for owner
    transfers, discretionary equity trades, share-adjusted dividends, and
    financing. Option activity and assignment/exercise delivery stay out.
    """
    start = _frozen_start(
        position_history=position_history,
        daily_bars=daily_bars,
        actual_points=actual_points,
    )
    if isinstance(start, str):
        return _unavailable(start)
    anchor_day = start.anchor_day
    account_executions = _rows_for_account(executions, start.account_id)
    account_movements = _rows_for_account(cash_movements, start.account_id)
    account_lifecycle = _rows_for_account(lifecycle_events, start.account_id)
    quantities = dict(start.quantities)
    shorted, carried = start.shorted, dict(start.carried)
    cash = start.cash_residual
    forced_keys, uncertain_days = classify_forced_equity(
        executions=account_executions,
        lifecycle_events=account_lifecycle,
    )
    points: list[ReturnPoint] = []
    previous: Decimal | None = None
    cumulative_factor = Decimal("1")
    chain_complete = True
    previous_day = anchor_day
    omitted_days = 0
    interest_paid = ZERO
    for day, _opening_stock in start.stock_series:
        candidate_cash = cash
        candidate_quantities = dict(quantities)
        candidate_interest = ZERO
        elapsed = (day - previous_day).days
        if candidate_cash < ZERO and elapsed > 0 and day != anchor_day:
            charge = (
                -candidate_cash
                * annual_interest_rate_percent
                / HUNDRED
                * Decimal(elapsed)
                / INTEREST_DAY_COUNT
            )
            candidate_cash -= charge
            candidate_interest = charge
        flow = _flow_into(account_movements, after=previous_day, through=day, anchor=anchor_day)
        candidate_cash += flow
        candidate_quantities, candidate_cash, omitted = apply_discretionary_equity(
            candidate_quantities,
            candidate_cash,
            executions=account_executions,
            after=previous_day,
            through=day,
            forced_keys=forced_keys,
            uncertain_symbol_days=uncertain_days,
            account=start.account_id,
        )
        day_dividends = (
            _scaled_dividends_between(
                account_movements,
                candidate_quantities,
                position_history,
                after=previous_day,
                through=day,
            )
            if day > anchor_day
            else ZERO
        )
        candidate_cash += day_dividends
        stock_value, day_carried = _value_lots(daily_bars, candidate_quantities, day)
        if stock_value is None:
            continue
        if omitted:
            omitted_days += 1
        cash = candidate_cash
        quantities = candidate_quantities
        interest_paid += candidate_interest
        carried.update(day_carried)
        value = stock_value + cash
        daily_return: Decimal | None = None
        if previous is not None:
            if previous == ZERO:
                chain_complete = False
            else:
                daily_return = (value - previous - flow) / previous * HUNDRED
                cumulative_factor *= Decimal("1") + daily_return / HUNDRED
        point_quality = "estimated" if day_carried or omitted else "derived"
        points.append(
            ReturnPoint(
                date=day,
                value=value,
                external_flow=flow,
                daily_return_percent=daily_return,
                interval_return_percent=daily_return,
                cumulative_return_percent=(
                    (cumulative_factor - Decimal("1")) * HUNDRED if chain_complete else None
                ),
                quality="derived_price_only",
                value_quality=point_quality,
                return_quality=point_quality if daily_return is not None else "unresolved",
                valuation_phase="close",
            )
        )
        previous = value
        previous_day = day
    final_return = points[-1].cumulative_return_percent if len(points) >= 2 else None
    note = (
        "Starting long stock lots plus later discretionary share trades. Assignment and "
        "exercise delivery is ignored; expiration has no stock delivery. Option premium "
        "and marks stay out. The opening non-stock cash residual remains frozen except for "
        "financing and the listed cash events. Owner "
        "transfers arrive as idle cash and returns are chained time-weighted, matching "
        "the managed book. Dividends scale to the freeze's lots versus live lots that day."
    )
    if interest_paid:
        note = (
            f"{note} Borrow on the frozen residual is charged "
            f"{annual_interest_rate_percent:.2f}% on a 360-day basis."
        )
    if omitted_days:
        note = (
            f"{note} {omitted_days} session(s) had an ambiguous assignment/exercise share "
            "print, so that account-symbol-day was not copied."
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
        note = (
            f"{note} One or more sessions used the most recent stored price for {held_flat}; "
            "those points are marked estimated."
        )
    status = (
        "waiting"
        if final_return is None
        else "estimated"
        if omitted_days
        else "carried_forward"
        if carried
        else "derived"
    )
    return ComparisonSeries(
        key="shares_without_options",
        label="Starting stock plus your share trades",
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
    anchor_day = start.anchor_day
    account_movements = _rows_for_account(cash_movements, start.account_id)
    sessions = tuple(day for day, _value in start.stock_series)
    aligned = _aligned_market_closes(daily_bars, symbol=symbol, sessions=sessions)
    if aligned is None:
        return _levered_unavailable(
            symbol,
            f"A positive, unambiguous {symbol} close path is not stored for the anchored window.",
        )
    prices, carried = aligned
    anchor_close = prices[0][1]
    shares = start.exposure / anchor_close
    # Negative cash is the margin debit that funds exposure above net liquidation.
    cash = start.cash_residual
    financed = cash < ZERO
    points: list[ReturnPoint] = []
    previous: Decimal | None = None
    cumulative_factor = Decimal("1")
    chain_complete = True
    previous_day = anchor_day
    interest_paid = ZERO
    for day, close in prices:
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
        flow = _flow_into(account_movements, after=previous_day, through=day, anchor=anchor_day)
        cash += flow
        value = shares * close + cash
        daily_return: Decimal | None = None
        if previous is not None:
            if previous == ZERO:
                chain_complete = False
            else:
                daily_return = (value - previous - flow) / previous * HUNDRED
                cumulative_factor *= Decimal("1") + daily_return / HUNDRED
        points.append(
            ReturnPoint(
                date=day,
                value=value,
                external_flow=flow,
                daily_return_percent=daily_return,
                interval_return_percent=daily_return,
                cumulative_return_percent=(
                    (cumulative_factor - Decimal("1")) * HUNDRED if chain_complete else None
                ),
                quality="derived_levered",
                value_quality="estimated" if day in carried else "derived",
                return_quality=(
                    "estimated"
                    if daily_return is not None and day in carried
                    else "derived"
                    if daily_return is not None
                    else "unresolved"
                ),
                valuation_phase="close",
            )
        )
        previous = value
        previous_day = day
    if len(points) < 2 or not chain_complete:
        return _levered_unavailable(
            symbol,
            (
                f"Fewer than two {symbol} closes fall inside the anchored window."
                if len(points) < 2
                else "The leverage-matched portfolio reached a zero value, so its return "
                "chain cannot continue."
            ),
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
    if carried:
        note = (
            f"{note} {len(carried)} missing {symbol} session"
            f"{'s were' if len(carried) != 1 else ' was'} held at the last stored close and "
            "marked estimated."
        )
    return ComparisonSeries(
        key="levered_market_reference",
        label=f"{symbol} at your exposure",
        status="carried_forward" if carried else "derived_levered",
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
    sessions = tuple(point.date for point in actual_points)
    aligned = _aligned_market_closes(daily_bars, symbol=symbol, sessions=sessions)
    if aligned is None:
        return _market_unavailable(symbol)
    rows, carried = aligned
    if len(rows) < 2:
        return _market_unavailable(symbol)
    first = rows[0][1]
    previous: Decimal | None = None
    built: list[ReturnPoint] = []
    previous = None
    for day, value in rows:
        daily_return: Decimal | None = (value - previous) / previous * HUNDRED if previous else None
        built.append(
            ReturnPoint(
                date=day,
                value=value,
                external_flow=ZERO,
                daily_return_percent=daily_return,
                interval_return_percent=daily_return,
                cumulative_return_percent=(value - first) / first * HUNDRED,
                quality="price_only",
                value_quality="estimated" if day in carried else "derived",
                return_quality=(
                    "estimated"
                    if daily_return is not None and day in carried
                    else "derived"
                    if daily_return is not None
                    else "unresolved"
                ),
                valuation_phase="close",
            )
        )
        previous = value
    return ComparisonSeries(
        key="market_reference",
        label=f"{symbol} price",
        status="carried_forward" if carried else "price_only",
        return_percent=built[-1].cumulative_return_percent,
        method_note=(
            f"{symbol} close-to-close price return. Dividends are not included."
            + (
                f" {len(carried)} missing session"
                f"{'s use' if len(carried) != 1 else ' uses'} the last stored close and "
                "is marked estimated."
                if carried
                else ""
            )
        ),
        points=tuple(built),
    )


def _aligned_market_closes(
    rows: Sequence[dict[str, Any]],
    *,
    symbol: str,
    sessions: Sequence[date],
) -> tuple[list[tuple[date, Decimal]], dict[date, date]] | None:
    """Align a market reference to managed sessions without hiding gaps.

    A short internal data gap is represented by an estimated carry. Longer gaps,
    a missing opening anchor, non-positive values, or conflicting duplicate bars
    make the reference unavailable instead of drawing a confident straight line.
    """

    ordered_sessions = sorted(set(sessions))
    if not ordered_sessions:
        return None
    start, end = ordered_sessions[0], ordered_sessions[-1]
    values_by_day: defaultdict[date, set[Decimal]] = defaultdict(set)
    for row in rows:
        day = row.get("trade_date")
        if (
            str(row.get("symbol") or "").upper() != symbol.upper()
            or not isinstance(day, date)
            or not start <= day <= end
            or row.get("close") is None
        ):
            continue
        values_by_day[day].add(Decimal(str(row["close"])))
    if any(len(values) != 1 or next(iter(values)) <= ZERO for values in values_by_day.values()):
        return None
    closes = {day: next(iter(values)) for day, values in values_by_day.items()}
    if start not in closes:
        return None

    # A carry is acceptable only inside two observed closes. Extending the
    # benchmark past its latest published close would compare a live managed
    # day with a frozen market and distort the headline difference.
    last_observed_session = max(closes)
    covered_sessions = tuple(day for day in ordered_sessions if day <= last_observed_session)

    result: list[tuple[date, Decimal]] = []
    carried: dict[date, date] = {}
    latest_observed_day: date | None = None
    latest_close: Decimal | None = None
    missing_run = 0
    for day in covered_sessions:
        close = closes.get(day)
        if close is not None:
            latest_observed_day = day
            latest_close = close
            missing_run = 0
        else:
            missing_run += 1
            if (
                latest_observed_day is None
                or latest_close is None
                or missing_run > MAX_CARRIED_MARKET_SESSIONS
            ):
                return None
            close = latest_close
            carried[day] = latest_observed_day
        result.append((day, close))
    return result, carried


def _snapshots_by_observation(
    rows: Sequence[dict[str, Any]],
) -> list[tuple[date, tuple[dict[str, Any], ...]]]:
    grouped: dict[tuple[str, date], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        observed = row.get("observed_at")
        if observed is not None:
            grouped[(str(row.get("sync_run_id") or observed), market_date(observed))].append(row)
    snapshots = [
        (
            day,
            tuple(items),
            max(_observation_timestamp(row.get("observed_at")) for row in items),
            run,
        )
        for (run, day), items in grouped.items()
    ]
    return [
        (day, items)
        for day, items, _observed, _run in sorted(
            snapshots,
            key=lambda item: (item[0], item[2], item[3]),
        )
    ]


def _observation_timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    return datetime.min.replace(tzinfo=UTC)


def _rows_for_account(rows: Sequence[dict[str, Any]], account: str) -> tuple[dict[str, Any], ...]:
    if not account:
        return tuple(rows)
    return tuple(
        row
        for row in rows
        if str(row.get("account_id") or row.get("account_mask") or "").strip().casefold()
        in {"", account}
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
        if str(row.get("asset_type") or "").upper() not in {"EQUITY", "ETF", "STOCK"}:
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
    sessions: Sequence[date],
) -> tuple[list[tuple[date, Decimal]], dict[str, date]]:
    """Value the frozen lots each day, holding a lapsed symbol at its last close.

    A position closed early in the window stops receiving fresh bars, and
    requiring every frozen symbol to price on the same day let one lapsed
    ticker truncate the entire counterfactual — discarding sessions the
    remaining holdings priced perfectly well. Carrying the last observed close
    keeps the comparison running; the caller reports which symbols were carried
    so a held-flat price is never mistaken for an observed one.
    """

    if not sessions:
        return [], {}
    start, end = min(sessions), max(sessions)
    closes: dict[str, dict[date, Decimal]] = defaultdict(dict)
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        day = row.get("trade_date")
        if (
            symbol in quantities
            and isinstance(day, date)
            and day <= end
            and row.get("close") is not None
            and Decimal(str(row["close"])) > ZERO
        ):
            closes[symbol][day] = Decimal(str(row["close"]))

    # The counterfactual must have exactly the managed book's valuation dates.
    # Dates from an unrelated option or benchmark bar must never create a fake
    # account session.
    grid = sorted({day for day in sessions if start <= day <= end})
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
    return external_flow_between_instants(
        cash_movements,
        after=_market_close(after),
        through=_market_close(through),
    )


def _market_close(day: date) -> datetime:
    return datetime.combine(day, time(16, 0), tzinfo=MARKET_TIME_ZONE).astimezone(UTC)


def _value_lots(
    rows: Sequence[dict[str, Any]],
    quantities: dict[str, Decimal],
    day: date,
) -> tuple[Decimal | None, dict[str, date]]:
    if not quantities:
        return ZERO, {}
    closes: dict[str, dict[date, Decimal]] = defaultdict(dict)
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        trade_day = row.get("trade_date")
        if (
            symbol in quantities
            and isinstance(trade_day, date)
            and trade_day <= day
            and row.get("close") is not None
            and Decimal(str(row["close"])) > ZERO
        ):
            closes[symbol][trade_day] = Decimal(str(row["close"]))
    priced: dict[str, Decimal] = {}
    carried: dict[str, date] = {}
    for symbol in quantities:
        observed = [known for known in closes.get(symbol, {}) if known <= day]
        if not observed:
            return None, {}
        latest = max(observed)
        priced[symbol] = closes[symbol][latest]
        if latest != day:
            carried[symbol] = latest
    return sum((quantities[symbol] * priced[symbol] for symbol in quantities), ZERO), carried


def _scaled_dividends_between(
    rows: Sequence[dict[str, Any]],
    quantities: dict[str, Decimal],
    position_history: Sequence[dict[str, Any]],
    *,
    after: date,
    through: date,
) -> Decimal:
    total = ZERO
    for row in rows:
        if str(row.get("movement_type") or "").lower() != "dividend":
            continue
        occurred = movement_date(row.get("occurred_at"))
        if occurred is None or not after < occurred <= through:
            continue
        symbol = str(row.get("symbol") or "").upper()
        freeze_qty = quantities.get(symbol, ZERO)
        live_qty = live_long_quantity(position_history, symbol, occurred)
        if live_qty is None:
            live_qty = freeze_qty
        total += scaled_dividend(row, freeze_qty=freeze_qty, live_qty=live_qty)
    return total


def _unavailable(note: str) -> ComparisonSeries:
    return ComparisonSeries(
        key="shares_without_options",
        label="Starting stock plus your share trades",
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
