from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal

from schwab_dashboard.application.dashboard.live_option_clocks import remaining_open_lot_date
from schwab_dashboard.application.dashboard.models import (
    LiveOpenOptionPosition,
    LivePositionBook,
    LiveUnderlyingPosition,
    PositionSummary,
    UnmodeledShortOption,
)
from schwab_dashboard.application.expiration import assess_option_expiration
from schwab_dashboard.application.market_time import (
    market_date,
    option_session_state,
    quote_session_state,
)
from schwab_dashboard.application.option_lifecycle import option_side
from schwab_dashboard.application.rolls.collect import collect_roll_quotes
from schwab_dashboard.application.values import sum_if_complete

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def build_live_position_book(
    positions: Sequence[PositionSummary],
    *,
    as_of: date | datetime,
    evaluated_at: date | datetime | None = None,
    option_market: Sequence[Mapping[str, object]] = (),
    underlying_market: Sequence[Mapping[str, object]] = (),
    daily_bars: Sequence[Mapping[str, object]] = (),
    executions: Sequence[Mapping[str, object]] = (),
) -> LivePositionBook:
    as_of_date = market_date(as_of)
    session_clock = evaluated_at if evaluated_at is not None else as_of
    quote_clock = session_clock if isinstance(session_clock, datetime) else None
    option_quotes = {_canonical(str(row["symbol"])): row for row in option_market}
    underlying_quotes = {_canonical(str(row["symbol"])): row for row in underlying_market}
    holdings_by_symbol: defaultdict[str, list[PositionSummary]] = defaultdict(list)
    holdings_by_account_symbol: defaultdict[tuple[str, str], list[PositionSummary]] = defaultdict(
        list
    )
    for position in positions:
        is_share_holding = _asset_type(position.asset_type) in {"equity", "etf", "stock"}
        if not is_share_holding or position.quantity <= ZERO:
            continue
        symbol_key = _canonical(position.symbol)
        holdings_by_symbol[symbol_key].append(position)
        holdings_by_account_symbol[(_account_scope(position), symbol_key)].append(position)
    calls_by_symbol: defaultdict[str, list[LiveOpenOptionPosition]] = defaultdict(list)
    puts_by_symbol: defaultdict[str, list[LiveOpenOptionPosition]] = defaultdict(list)
    unmodeled_short_options: list[UnmodeledShortOption] = []
    for position in positions:
        multiplier, multiplier_source = _resolved_contract_multiplier(position)
        issue = _short_option_model_issue(position, multiplier=multiplier)
        if issue is not None:
            unmodeled_short_options.append(
                UnmodeledShortOption(
                    option_symbol=position.symbol,
                    reported_contracts=abs(position.quantity),
                    reason=issue,
                    account_mask=position.account_mask,
                    account_id=position.account_id,
                )
            )
            continue
        if not _is_short_option(position, multiplier=multiplier):
            continue
        assert position.underlying_symbol is not None
        assert position.expiration_date is not None
        assert position.strike is not None
        contracts = int(abs(position.quantity))
        underlying_key = _canonical(position.underlying_symbol)
        account_holdings = holdings_by_account_symbol.get(
            (_account_scope(position), underlying_key),
            (),
        )
        # A security's mark is account-independent, so another account's same-
        # symbol holding remains a valid price fallback. Share coverage below is
        # still strictly account-scoped and never borrows those shares.
        matching_holdings = account_holdings or holdings_by_symbol.get(underlying_key, ())
        underlying_quote = underlying_quotes.get(_canonical(position.underlying_symbol), {})
        quoted_underlying_price = _optional_decimal(underlying_quote.get("mark"))
        underlying_price = (
            quoted_underlying_price
            if quoted_underlying_price is not None
            else _weighted_holding_value(matching_holdings, field="mark")
        )
        quote = option_quotes.get(_canonical(position.symbol), {})
        normalized_option_type = option_side(position.option_type)
        assert normalized_option_type is not None
        option_type = normalized_option_type.upper()
        assert multiplier is not None
        deliverable_shares = _resolved_share_deliverable(
            position,
            premium_multiplier=multiplier,
        )
        session_state = option_session_state(position.expiration_date, session_clock)
        official_expiration_close = _official_expiration_close(
            position.underlying_symbol,
            expires_on=position.expiration_date,
            daily_bars=daily_bars,
        )
        opened_on = remaining_open_lot_date(
            position.symbol,
            executions,
            account_id=position.account_id,
            account_mask=position.account_mask,
        )
        distance = (
            position.strike - underlying_price
            if option_type == "CALL" and underlying_price is not None
            else underlying_price - position.strike
            if underlying_price is not None
            else None
        )
        distance_percent = (
            distance / underlying_price * HUNDRED
            if distance is not None and underlying_price
            else None
        )
        quoted_option_mark = _optional_decimal(quote.get("mark"))
        option = LiveOpenOptionPosition(
            account_mask=position.account_mask,
            option_symbol=position.symbol,
            underlying_symbol=position.underlying_symbol,
            contracts=contracts,
            expires_on=position.expiration_date,
            days_to_expiration=max(0, (position.expiration_date - as_of_date).days),
            strike=position.strike,
            entry_credit_per_share=position.average_price,
            estimated_mark_per_share=(
                quoted_option_mark if quoted_option_mark is not None else position.mark
            ),
            market_value=position.market_value,
            open_profit_loss=position.open_profit_loss,
            day_profit_loss=position.day_profit_loss,
            underlying_price=underlying_price,
            strike_distance_per_share=distance,
            strike_distance_percent=distance_percent,
            bid_per_share=_optional_decimal(quote.get("bid")),
            ask_per_share=_optional_decimal(quote.get("ask")),
            implied_volatility_percent=_optional_decimal(quote.get("implied_volatility")),
            delta=_optional_decimal(quote.get("delta")),
            gamma=_optional_decimal(quote.get("gamma")),
            theta_per_share=_optional_decimal(quote.get("theta")),
            vega=_optional_decimal(quote.get("vega")),
            rho=_optional_decimal(quote.get("rho")),
            volume=_optional_int(quote.get("volume")),
            open_interest=_optional_int(quote.get("open_interest")),
            quote_observed_at=quote.get("observed_at"),  # type: ignore[arg-type]
            quote_quality=str(quote.get("quote_quality") or "") or None,
            option_type=option_type,
            contract_multiplier=multiplier,
            multiplier_source=multiplier_source,
            deliverable_shares_per_contract=deliverable_shares,
            roll_quote_candidates=(
                collect_roll_quotes(
                    underlying_symbol=position.underlying_symbol or position.symbol,
                    option_side=option_type,
                    source_expiration=position.expiration_date,
                    source_strike=position.strike,
                    source_option_symbol=position.symbol,
                    option_market=option_market,
                )
                if session_state.can_close_or_roll
                and deliverable_shares is not None
                and position.expiration_date is not None
                and position.strike is not None
                else ()
            ),
            session_state=session_state,
            underlying_previous_close=_optional_decimal(underlying_quote.get("previous_close")),
            underlying_week_reference_price=_weekly_reference_price(
                position.underlying_symbol,
                daily_bars=daily_bars,
                as_of=as_of_date,
            ),
            opened_on=opened_on,
            original_days_to_expiration=(
                max(0, (position.expiration_date - opened_on).days)
                if opened_on is not None
                else None
            ),
            expiration_assessment=(
                assess_option_expiration(
                    option_side=option_type,
                    session_state=session_state,
                    strike=position.strike,
                    contracts=contracts,
                    deliverable_shares_per_contract=deliverable_shares,
                    official_close=official_expiration_close,
                    latest_underlying_price=underlying_price,
                )
                if deliverable_shares is not None
                else None
            ),
            account_id=position.account_id,
        )
        if option_type == "CALL":
            calls_by_symbol[underlying_key].append(option)
        else:
            puts_by_symbol[underlying_key].append(option)

    underlyings: list[LiveUnderlyingPosition] = []
    all_calls: list[LiveOpenOptionPosition] = []
    all_puts: list[LiveOpenOptionPosition] = []
    symbols = sorted(set(calls_by_symbol) | set(puts_by_symbol))
    for symbol in symbols:
        calls = calls_by_symbol[symbol]
        puts = puts_by_symbol[symbol]
        ordered_calls = tuple(sorted(calls, key=lambda item: (item.expires_on, item.strike)))
        ordered_puts = tuple(sorted(puts, key=lambda item: (item.expires_on, item.strike)))
        all_calls.extend(ordered_calls)
        all_puts.extend(ordered_puts)
        holding_rows = tuple(holdings_by_symbol.get(_canonical(symbol), ()))
        share_quantity = sum((holding.quantity for holding in holding_rows), ZERO)
        shares = share_quantity
        underlying_quote = underlying_quotes.get(_canonical(symbol), {})
        # Account position marks can lag Schwab Market Data intraday. Quantity,
        # cost and account balances remain account-authoritative; quote-derived
        # price, value and session move come from the latest market snapshot.
        quoted_price = _optional_decimal(underlying_quote.get("mark"))
        current_price = (
            quoted_price
            if quoted_price is not None
            else _weighted_holding_value(holding_rows, field="mark")
        )
        previous_close = _optional_decimal(underlying_quote.get("previous_close"))
        quote_observed_at = _optional_datetime(underlying_quote.get("observed_at"))
        current_session_change_percent = _session_change_percent(
            current_price=current_price,
            previous_close=previous_close,
            fallback=_common_holding_value(holding_rows, field="day_profit_loss_percent"),
        )
        market_value = (
            current_price * share_quantity
            if quoted_price is not None and current_price is not None
            else sum_if_complete(holding.market_value for holding in holding_rows)
            if holding_rows
            else None
        )
        day_profit_loss = (
            (current_price - previous_close) * share_quantity
            if quoted_price is not None and current_price is not None and previous_close is not None
            else sum_if_complete(holding.day_profit_loss for holding in holding_rows)
            if holding_rows
            else None
        )
        open_contracts = sum(call.contracts for call in ordered_calls)
        covered_contracts, committed_shares, capacity = _account_scoped_share_coverage(
            holdings=holding_rows,
            calls=ordered_calls,
        )
        iv_values = [
            call.implied_volatility_percent
            for call in ordered_calls
            if call.implied_volatility_percent is not None
        ]
        underlyings.append(
            LiveUnderlyingPosition(
                symbol=symbol,
                description=_holding_description(holding_rows),
                shares=shares,
                average_price=_weighted_holding_value(holding_rows, field="average_price"),
                current_price=current_price,
                market_value=market_value,
                day_profit_loss=day_profit_loss,
                contract_capacity=capacity,
                open_call_contracts=open_contracts,
                covered_contracts=covered_contracts,
                uncovered_contracts=max(0, open_contracts - covered_contracts),
                coverage_percent=(committed_shares / shares * HUNDRED if shares else ZERO),
                open_mark_profit_loss=sum_if_complete(
                    call.open_profit_loss for call in ordered_calls
                ),
                calls=ordered_calls,
                average_open_iv_percent=(
                    sum(iv_values, ZERO) / Decimal(len(iv_values)) if iv_values else None
                ),
                estimated_theta_per_day=sum_if_complete(
                    (
                        -call.theta_per_share * call.position_scale
                        if call.theta_per_share is not None
                        else None
                    )
                    for call in ordered_calls
                    if call.can_close_or_roll
                ),
                puts=ordered_puts,
                estimated_put_theta_per_day=sum_if_complete(
                    (
                        -put.theta_per_share * put.position_scale
                        if put.theta_per_share is not None
                        else None
                    )
                    for put in ordered_puts
                    if put.can_close_or_roll
                ),
                previous_close=previous_close,
                current_session_change_percent=current_session_change_percent,
                quote_observed_at=quote_observed_at,
                quote_quality=str(underlying_quote.get("quote_quality") or "") or None,
                quote_session=quote_session_state(
                    quote_observed_at,
                    evaluated_at=session_clock,
                ),
                quote_evaluated_at=quote_clock,
            )
        )

    capacity = sum(item.contract_capacity for item in underlyings)
    open_contracts = sum(item.open_call_contracts for item in underlyings)
    covered_contracts = sum(item.covered_contracts for item in underlyings)
    total_shares = sum((item.shares for item in underlyings), ZERO)
    committed_shares = sum(
        (item.shares * item.coverage_percent / HUNDRED for item in underlyings),
        ZERO,
    )
    return LivePositionBook(
        underlyings=tuple(underlyings),
        calls=tuple(all_calls),
        total_shares=total_shares,
        contract_capacity=capacity,
        open_call_positions=len(all_calls),
        open_call_contracts=open_contracts,
        covered_contracts=covered_contracts,
        uncovered_contracts=sum(item.uncovered_contracts for item in underlyings),
        coverage_percent=(committed_shares / total_shares * HUNDRED if total_shares else ZERO),
        open_mark_profit_loss=sum_if_complete(call.open_profit_loss for call in all_calls),
        puts=tuple(all_puts),
        open_put_positions=len(all_puts),
        open_put_contracts=sum(put.contracts for put in all_puts),
        unmodeled_short_options=tuple(unmodeled_short_options),
    )


def _is_short_option(
    position: PositionSummary,
    *,
    multiplier: Decimal | None,
) -> bool:
    return (
        _asset_type(position.asset_type) == "option"
        and position.quantity < ZERO
        and abs(position.quantity) == abs(position.quantity).to_integral_value()
        and option_side(position.option_type) is not None
        and multiplier is not None
        and position.underlying_symbol is not None
        and position.expiration_date is not None
        and position.strike is not None
    )


def _short_option_model_issue(
    position: PositionSummary,
    *,
    multiplier: Decimal | None,
) -> str | None:
    """Explain why a reported short option cannot enter modeled totals."""

    if _asset_type(position.asset_type) != "option" or position.quantity >= ZERO:
        return None
    if abs(position.quantity) != abs(position.quantity).to_integral_value():
        return "Broker quantity is not a whole number of contracts."
    if multiplier is None:
        return "Premium multiplier is unavailable."
    if option_side(position.option_type) is None:
        return "Call or put side is unavailable."
    if position.underlying_symbol is None:
        return "Underlying symbol is unavailable."
    if position.expiration_date is None:
        return "Expiration date is unavailable."
    if position.strike is None:
        return "Strike is unavailable."
    return None


def _resolved_contract_multiplier(
    position: PositionSummary,
) -> tuple[Decimal | None, str | None]:
    """Resolve the premium/Greek scale without inventing adjusted terms.

    Current broker snapshots normally carry an explicit multiplier and
    standardness flag. Older snapshots may carry neither. For those rows, a
    conventional OCC symbol with a non-numeric root is enough to retain the
    position with an assumed 100-unit premium scale. Numeric option roots and
    text that identifies an adjustment stay unknown instead of being guessed.
    """

    explicit = position.contract_multiplier
    if explicit is not None:
        if explicit <= ZERO:
            return None, position.multiplier_source or "invalid"
        return abs(explicit), position.multiplier_source or "exported"
    if position.is_non_standard is True:
        return None, "unknown_adjusted"
    if position.is_non_standard is False:
        return HUNDRED, position.multiplier_source or "standard_flag"

    signal = f"{position.symbol} {position.description}".upper()
    if any(token in signal for token in ("ADJUSTED", " ADJ ", "NON-STANDARD", "NONSTANDARD")):
        return None, "unknown_adjusted"
    root = _occ_root(position.symbol)
    if root is not None and not any(character.isdigit() for character in root):
        return HUNDRED, position.multiplier_source or "assumed_standard"
    return None, position.multiplier_source or "unknown"


def _resolved_share_deliverable(
    position: PositionSummary,
    *,
    premium_multiplier: Decimal,
) -> Decimal | None:
    """Return stock delivered per contract only when that term is supported.

    Schwab's multiplier scales option premiums. It is also the share
    deliverable for a standard equity option, but an adjusted contract may
    deliver cash or other securities. Treat adjusted or suspicious legacy
    contracts as unresolved instead of converting their premium scale into a
    fabricated share obligation.
    """

    if position.is_non_standard is True:
        return None
    if position.is_non_standard is False:
        return premium_multiplier
    signal = f"{position.symbol} {position.description}".upper()
    if any(token in signal for token in ("ADJUSTED", " ADJ ", "NON-STANDARD", "NONSTANDARD")):
        return None
    root = _occ_root(position.symbol)
    if (
        premium_multiplier == HUNDRED
        and root is not None
        and not any(character.isdigit() for character in root)
    ):
        return HUNDRED
    return None


def _occ_root(symbol: str) -> str | None:
    normalized = symbol.strip().upper()
    if len(normalized) <= 15:
        return None
    root = normalized[:-15].strip()
    tail = normalized[-15:]
    if not root or not tail[:6].isdigit() or tail[6:7] not in {"C", "P"}:
        return None
    return root if tail[7:].isdigit() else None


def _session_change_percent(
    *,
    current_price: Decimal | None,
    previous_close: Decimal | None,
    fallback: Decimal | None,
) -> Decimal | None:
    if current_price is None or previous_close is None or previous_close <= ZERO:
        return fallback
    return (current_price / previous_close - Decimal("1")) * HUNDRED


def _weekly_reference_price(
    symbol: str,
    *,
    daily_bars: Sequence[Mapping[str, object]],
    as_of: date,
) -> Decimal | None:
    rows = sorted(
        (
            row
            for row in daily_bars
            if _canonical(str(row.get("symbol") or "")) == _canonical(symbol)
            and row.get("trade_date") is not None
            and (_optional_decimal(row.get("close")) or ZERO) > ZERO
        ),
        key=lambda row: _date(row.get("trade_date")),
    )
    if not rows:
        return None

    expected_session = as_of
    while expected_session.weekday() >= 5:
        expected_session = expected_session.fromordinal(expected_session.toordinal() - 1)
    latest_date = _date(rows[-1].get("trade_date"))
    offset = 6 if latest_date >= expected_session else 5
    if len(rows) < offset:
        return None
    return _optional_decimal(rows[-offset].get("close"))


def _official_expiration_close(
    symbol: str,
    *,
    expires_on: date,
    daily_bars: Sequence[Mapping[str, object]],
) -> Decimal | None:
    """Return only an exact expiration-session close, never a nearby proxy."""

    matches = [
        row
        for row in daily_bars
        if _canonical(str(row.get("symbol") or "")) == _canonical(symbol)
        and row.get("trade_date") is not None
        and _date(row.get("trade_date")) == expires_on
        and (_optional_decimal(row.get("close")) or ZERO) > ZERO
    ]
    if not matches:
        return None
    return _optional_decimal(matches[-1].get("close"))


def _optional_datetime(value: object) -> datetime | None:
    return value if isinstance(value, datetime) else None


def _share_coverage(
    shares: Decimal,
    calls: Sequence[LiveOpenOptionPosition],
) -> tuple[int, Decimal, Decimal]:
    remaining = max(ZERO, shares)
    covered = 0
    committed = ZERO
    known_calls = tuple(call for call in calls if call.deliverable_shares_per_contract is not None)
    for call in sorted(
        known_calls,
        key=lambda item: item.deliverable_shares_per_contract or ZERO,
    ):
        deliverable_shares = call.deliverable_shares_per_contract
        assert deliverable_shares is not None
        if deliverable_shares <= ZERO:
            continue
        count = min(call.contracts, int(remaining // deliverable_shares))
        covered += count
        used = Decimal(count) * deliverable_shares
        committed += used
        remaining -= used
    return covered, committed, remaining


def _account_scoped_share_coverage(
    *,
    holdings: Sequence[PositionSummary],
    calls: Sequence[LiveOpenOptionPosition],
) -> tuple[int, Decimal, int]:
    """Measure call coverage without moving shares between brokerage accounts."""

    shares_by_account: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
    calls_by_account: defaultdict[str, list[LiveOpenOptionPosition]] = defaultdict(list)
    for holding in holdings:
        shares_by_account[_account_scope(holding)] += holding.quantity
    for call in calls:
        calls_by_account[_account_scope(call)].append(call)

    covered = 0
    committed = ZERO
    capacity = 0
    for account_mask in set(shares_by_account) | set(calls_by_account):
        account_shares = max(ZERO, shares_by_account[account_mask])
        account_covered, account_committed, remaining = _share_coverage(
            account_shares,
            calls_by_account[account_mask],
        )
        covered += account_covered
        committed += account_committed
        capacity += account_covered + int(remaining // HUNDRED)
    return covered, committed, capacity


def _weighted_holding_value(
    holdings: Sequence[PositionSummary],
    *,
    field: str,
) -> Decimal | None:
    """Combine per-account prices only when every contributing row is complete."""

    if not holdings:
        return None
    numerator = ZERO
    denominator = ZERO
    for holding in holdings:
        value = getattr(holding, field)
        if value is None:
            return None
        numerator += value * holding.quantity
        denominator += holding.quantity
    return numerator / denominator if denominator > ZERO else None


def _common_holding_value(
    holdings: Sequence[PositionSummary],
    *,
    field: str,
) -> Decimal | None:
    """Return a shared security-level value, withholding conflicting account rows."""

    values = [getattr(holding, field) for holding in holdings]
    if not values or any(value is None for value in values):
        return None
    first = values[0]
    return first if all(value == first for value in values[1:]) else None


def _holding_description(holdings: Sequence[PositionSummary]) -> str:
    return next(
        (holding.description for holding in holdings if holding.description.strip()),
        "No matching long shares",
    )


def _canonical(value: str) -> str:
    return "".join(value.upper().split())


def _account_scope(position: PositionSummary | LiveOpenOptionPosition) -> str:
    return str(position.account_id or position.account_mask).strip().casefold()


def _asset_type(value: object) -> str:
    return str(value or "").strip().casefold().split(".")[-1]


def _optional_decimal(value: object) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _optional_int(value: object) -> int | None:
    return int(str(value)) if value is not None else None


def _date(value: object) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
