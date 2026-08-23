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
)
from schwab_dashboard.application.expiration import assess_option_expiration
from schwab_dashboard.application.market_time import (
    market_date,
    option_session_state,
    quote_session_state,
)
from schwab_dashboard.application.rolls.collect import collect_roll_quotes

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
    holdings = {
        position.symbol: position
        for position in positions
        if position.asset_type.upper() != "OPTION" and position.quantity > ZERO
    }
    calls_by_symbol: defaultdict[str, list[LiveOpenOptionPosition]] = defaultdict(list)
    puts_by_symbol: defaultdict[str, list[LiveOpenOptionPosition]] = defaultdict(list)
    for position in positions:
        if not _is_short_option(position):
            continue
        assert position.underlying_symbol is not None
        assert position.expiration_date is not None
        assert position.strike is not None
        contracts = int(abs(position.quantity))
        holding = holdings.get(position.underlying_symbol)
        underlying_quote = underlying_quotes.get(_canonical(position.underlying_symbol), {})
        quoted_underlying_price = _optional_decimal(underlying_quote.get("mark"))
        underlying_price = (
            quoted_underlying_price
            if quoted_underlying_price is not None
            else holding.mark
            if holding is not None
            else None
        )
        quote = option_quotes.get(_canonical(position.symbol), {})
        option_type = str(position.option_type or "").upper()
        session_state = option_session_state(position.expiration_date, session_clock)
        official_expiration_close = _official_expiration_close(
            position.underlying_symbol,
            expires_on=position.expiration_date,
            daily_bars=daily_bars,
        )
        opened_on = remaining_open_lot_date(position.symbol, executions)
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
        option = LiveOpenOptionPosition(
            account_mask=position.account_mask,
            option_symbol=position.symbol,
            underlying_symbol=position.underlying_symbol,
            contracts=contracts,
            expires_on=position.expiration_date,
            days_to_expiration=max(0, (position.expiration_date - as_of_date).days),
            strike=position.strike,
            entry_credit_per_share=position.average_price,
            estimated_mark_per_share=_optional_decimal(quote.get("mark")) or position.mark,
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
            contract_multiplier=position.contract_multiplier or HUNDRED,
            multiplier_source=position.multiplier_source,
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
            expiration_assessment=assess_option_expiration(
                option_side=option_type,
                session_state=session_state,
                strike=position.strike,
                contracts=contracts,
                contract_multiplier=position.contract_multiplier or HUNDRED,
                official_close=official_expiration_close,
                latest_underlying_price=underlying_price,
            ),
        )
        if option_type == "CALL":
            calls_by_symbol[position.underlying_symbol].append(option)
        else:
            puts_by_symbol[position.underlying_symbol].append(option)

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
        holding = holdings.get(symbol)
        shares = int(holding.quantity) if holding is not None else 0
        share_quantity = holding.quantity if holding is not None else ZERO
        underlying_quote = underlying_quotes.get(_canonical(symbol), {})
        # Account position marks can lag Schwab Market Data intraday. Quantity,
        # cost and account balances remain account-authoritative; quote-derived
        # price, value and session move come from the latest market snapshot.
        quoted_price = _optional_decimal(underlying_quote.get("mark"))
        current_price = (
            quoted_price
            if quoted_price is not None
            else holding.mark
            if holding is not None
            else None
        )
        previous_close = _optional_decimal(underlying_quote.get("previous_close"))
        quote_observed_at = _optional_datetime(underlying_quote.get("observed_at"))
        current_session_change_percent = _session_change_percent(
            current_price=current_price,
            previous_close=previous_close,
            fallback=(holding.day_profit_loss_percent if holding is not None else None),
        )
        market_value = (
            current_price * share_quantity
            if quoted_price is not None and current_price is not None
            else holding.market_value
            if holding is not None
            else None
        )
        day_profit_loss = (
            (current_price - previous_close) * share_quantity
            if quoted_price is not None and current_price is not None and previous_close is not None
            else holding.day_profit_loss
            if holding is not None
            else None
        )
        capacity = _contract_capacity(shares, ordered_calls)
        open_contracts = sum(call.contracts for call in ordered_calls)
        covered_contracts = _covered_contracts(shares, ordered_calls)
        iv_values = [
            call.implied_volatility_percent
            for call in ordered_calls
            if call.implied_volatility_percent is not None
        ]
        underlyings.append(
            LiveUnderlyingPosition(
                symbol=symbol,
                description=holding.description
                if holding is not None
                else "No matching long shares",
                shares=shares,
                average_price=holding.average_price if holding is not None else None,
                current_price=current_price,
                market_value=market_value,
                day_profit_loss=day_profit_loss,
                contract_capacity=capacity,
                open_call_contracts=open_contracts,
                covered_contracts=covered_contracts,
                uncovered_contracts=max(0, open_contracts - capacity),
                coverage_percent=(
                    Decimal(covered_contracts) / Decimal(capacity) * HUNDRED if capacity else ZERO
                ),
                open_mark_profit_loss=sum(
                    (call.open_profit_loss or ZERO for call in ordered_calls), ZERO
                ),
                calls=ordered_calls,
                average_open_iv_percent=(
                    sum(iv_values, ZERO) / Decimal(len(iv_values)) if iv_values else None
                ),
                estimated_theta_per_day=sum(
                    (
                        -(call.theta_per_share or ZERO)
                        * call.contract_multiplier
                        * Decimal(call.contracts)
                        for call in ordered_calls
                        if call.can_close_or_roll
                    ),
                    ZERO,
                ),
                puts=ordered_puts,
                estimated_put_theta_per_day=sum(
                    (
                        -(put.theta_per_share or ZERO)
                        * put.contract_multiplier
                        * Decimal(put.contracts)
                        for put in ordered_puts
                        if put.can_close_or_roll
                    ),
                    ZERO,
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
    return LivePositionBook(
        underlyings=tuple(underlyings),
        calls=tuple(all_calls),
        total_shares=sum(item.shares for item in underlyings),
        contract_capacity=capacity,
        open_call_positions=len(all_calls),
        open_call_contracts=open_contracts,
        covered_contracts=covered_contracts,
        uncovered_contracts=sum(item.uncovered_contracts for item in underlyings),
        coverage_percent=(
            Decimal(covered_contracts) / Decimal(capacity) * HUNDRED if capacity else ZERO
        ),
        open_mark_profit_loss=sum((call.open_profit_loss or ZERO for call in all_calls), ZERO),
        puts=tuple(all_puts),
        open_put_positions=len(all_puts),
        open_put_contracts=sum(put.contracts for put in all_puts),
    )


def _is_short_option(position: PositionSummary) -> bool:
    return (
        position.asset_type.upper() == "OPTION"
        and position.quantity < ZERO
        and position.option_type in {"CALL", "PUT"}
        and position.underlying_symbol is not None
        and position.expiration_date is not None
        and position.strike is not None
    )


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
    ]
    if not matches:
        return None
    return _optional_decimal(matches[-1].get("close"))


def _optional_datetime(value: object) -> datetime | None:
    return value if isinstance(value, datetime) else None


def _covered_contracts(shares: int, calls: Sequence[LiveOpenOptionPosition]) -> int:
    remaining = max(0, shares)
    covered = 0
    for call in calls:
        deliverable_shares = int(call.contract_multiplier)
        if deliverable_shares <= 0:
            continue
        count = min(call.contracts, remaining // deliverable_shares)
        covered += count
        remaining -= count * deliverable_shares
    return covered


def _contract_capacity(shares: int, calls: Sequence[LiveOpenOptionPosition]) -> int:
    if not calls:
        return max(0, shares // 100)
    smallest_deliverable = min(
        (int(call.contract_multiplier) for call in calls if call.contract_multiplier > ZERO),
        default=100,
    )
    return max(0, shares // smallest_deliverable)


def _canonical(value: str) -> str:
    return "".join(value.upper().split())


def _optional_decimal(value: object) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _optional_int(value: object) -> int | None:
    return int(str(value)) if value is not None else None


def _date(value: object) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
