from __future__ import annotations

from datetime import UTC, datetime, time
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import OpenCallClock
from schwab_dashboard.application.dashboard.models import (
    DashboardSnapshot,
    LiveOpenOptionPosition,
)
from schwab_dashboard.application.risk.calculate import calculate_open_risk
from schwab_dashboard.application.risk.models import (
    OpenOptionRiskInput,
    OpenRiskSummary,
    UnderlyingEquityRiskInput,
)
from schwab_dashboard.domain.market import QuoteQuality


def build_open_risk_summary(snapshot: DashboardSnapshot) -> OpenRiskSummary | None:
    """Project the active short-option book into signed, coverage-aware risk."""
    live_book = snapshot.live_position_book
    if live_book is not None:
        live_options = tuple(
            option for option in (*live_book.calls, *live_book.puts) if option.can_close_or_roll
        )
        if any(option.underlying_price is None for option in live_options):
            return None
        options = tuple(
            _live_input(option, fallback_observed_at=snapshot.as_of) for option in live_options
        )
        equities = tuple(
            UnderlyingEquityRiskInput(
                symbol=item.symbol,
                shares=item.shares,
                underlying_price=_required_price(item.current_price),
            )
            for item in live_book.underlyings
        )
    else:
        options = tuple(
            _clock_input(
                underlying.symbol,
                underlying.current_price,
                clock,
                fallback_observed_at=snapshot.as_of,
                simulated=snapshot.is_demo,
            )
            for underlying in snapshot.underlyings
            for clock in underlying.open_call_clocks
            if clock.can_close_or_roll
        )
        equities = tuple(
            UnderlyingEquityRiskInput(
                symbol=underlying.symbol,
                shares=underlying.shares,
                underlying_price=underlying.current_price,
            )
            for underlying in snapshot.underlyings
        )
    return calculate_open_risk(options, equities=equities) if options else None


def _live_input(
    option: LiveOpenOptionPosition,
    *,
    fallback_observed_at: datetime,
) -> OpenOptionRiskInput:
    multiplier = abs(option.contract_multiplier)
    underlying_price = _required_price(option.underlying_price)
    return OpenOptionRiskInput(
        contract_key=option.option_symbol,
        symbol=option.underlying_symbol,
        contracts_short=Decimal(option.contracts),
        premium_multiplier=multiplier,
        deliverable_share_quantity=option.deliverable_shares_per_contract,
        strike=option.strike,
        underlying_price=underlying_price,
        observed_at=_aware_utc(option.quote_observed_at or fallback_observed_at),
        quote_quality=_quote_quality(option.quote_quality),
        entry_credit=option.entry_credit_per_share,
        option_mark=option.estimated_mark_per_share,
        bid=option.bid_per_share,
        ask=option.ask_per_share,
        delta=option.delta,
        gamma=option.gamma,
        theta=option.theta_per_share,
        vega=option.vega,
        option_type=option.option_type,
    )


def _required_price(value: Decimal | None) -> Decimal:
    if value is None:
        raise ValueError("underlying price is unavailable")
    return value


def _clock_input(
    symbol: str,
    underlying_price: Decimal,
    clock: OpenCallClock,
    *,
    fallback_observed_at: datetime,
    simulated: bool,
) -> OpenOptionRiskInput:
    observed_at = (
        datetime.combine(clock.quote_observed_on, time(21), tzinfo=UTC)
        if clock.quote_observed_on is not None
        else _aware_utc(fallback_observed_at)
    )
    return OpenOptionRiskInput(
        contract_key=clock.record_id,
        symbol=symbol,
        contracts_short=Decimal(clock.contracts),
        premium_multiplier=abs(clock.contract_multiplier),
        deliverable_share_quantity=clock.deliverable_shares_per_contract,
        strike=clock.strike,
        underlying_price=underlying_price,
        observed_at=observed_at,
        quote_quality=(QuoteQuality.COMPLETE if simulated else _quote_quality(clock.quote_status)),
        entry_credit=clock.entry_credit_per_share,
        option_mark=clock.mark_per_share,
        bid=clock.bid_per_share,
        ask=clock.close_ask_per_share,
        delta=clock.delta,
        gamma=clock.gamma,
        theta=clock.theta_per_share,
        vega=clock.vega,
        option_type="CALL",
    )


def _quote_quality(value: object) -> QuoteQuality:
    normalized = str(value or "unknown").strip().lower().replace(" ", "_")
    try:
        return QuoteQuality(normalized)
    except ValueError:
        return QuoteQuality.UNKNOWN


def _aware_utc(value: datetime) -> datetime:
    """Restore the UTC offset SQLite drops from otherwise normalized instants."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
