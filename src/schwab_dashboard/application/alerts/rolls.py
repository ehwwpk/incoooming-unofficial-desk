from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING

from schwab_dashboard.application.alerts.models import RollScenario
from schwab_dashboard.application.dashboard.covered_calls import OpenCallClock
from schwab_dashboard.application.rolls import (
    RollCandidate,
    RollQuote,
    RollSearchResult,
    RollSource,
    select_roll_candidates,
)
from schwab_dashboard.domain.instruments import OptionSide

if TYPE_CHECKING:
    from schwab_dashboard.application.dashboard.models import LiveOpenOptionPosition

D = Decimal
ZERO = D("0")


def build_call_roll_scenarios(
    call: OpenCallClock,
    *,
    current_price: Decimal,
    limit: int = 9,
    open_option_symbols: tuple[str, ...] = (),
) -> tuple[RollScenario, ...]:
    result = _call_roll_result(call, current_price=current_price, limit=limit)
    return tuple(
        _scenario(result.source, candidate, open_option_symbols=open_option_symbols)
        for candidate in result.candidates
    )


def no_clean_call_roll_reason(call: OpenCallClock, *, current_price: Decimal) -> str | None:
    result = _call_roll_result(call, current_price=current_price, limit=9)
    if any(candidate.strike > call.strike for candidate in result.candidates):
        return None
    return result.no_clean_reason


def build_put_roll_scenarios(
    put: LiveOpenOptionPosition,
    *,
    limit: int = 9,
    open_option_symbols: tuple[str, ...] = (),
) -> tuple[RollScenario, ...]:
    result = _put_roll_result(put, limit=limit)
    return tuple(
        _scenario(result.source, candidate, open_option_symbols=open_option_symbols)
        for candidate in result.candidates
    )


def no_clean_put_roll_reason(put: LiveOpenOptionPosition) -> str | None:
    return _put_roll_result(put, limit=9).no_clean_reason


def _call_roll_result(
    call: OpenCallClock,
    *,
    current_price: Decimal,
    limit: int,
) -> RollSearchResult:
    source = RollSource(
        symbol="",
        option_symbol=call.record_id,
        option_side=OptionSide.CALL,
        expires_on=call.expires_on,
        strike=call.strike,
        contracts=call.contracts,
        close_ask_per_share=call.close_ask_per_share,
        current_price=current_price,
        quote_status=call.quote_status,
    )
    quotes = tuple(
        RollQuote(
            option_symbol=quote.option_symbol,
            expires_on=quote.expires_on,
            strike=quote.strike,
            sell_bid_per_share=quote.sell_bid_per_share,
            quote_source=quote.quote_source,
            spread_percent=quote.spread_percent,
            open_interest=quote.open_interest,
            volume=quote.volume,
            theta_per_share=quote.theta_per_share,
        )
        for quote in call.roll_quote_candidates
        if call.can_close_or_roll
    )
    return select_roll_candidates(source, quotes, limit=limit)


def _put_roll_result(put: LiveOpenOptionPosition, *, limit: int) -> RollSearchResult:
    source = RollSource(
        symbol=put.underlying_symbol,
        option_symbol=put.option_symbol,
        option_side=OptionSide.PUT,
        expires_on=put.expires_on,
        strike=put.strike,
        contracts=put.contracts,
        close_ask_per_share=put.ask_per_share or put.estimated_mark_per_share or ZERO,
        current_price=put.underlying_price or ZERO,
        quote_status=(put.quote_quality or "unavailable").upper(),
        contract_multiplier=put.contract_multiplier,
    )
    return select_roll_candidates(
        source,
        put.roll_quote_candidates if put.can_close_or_roll else (),
        limit=limit,
    )


def _scenario(
    source: RollSource,
    candidate: RollCandidate,
    *,
    open_option_symbols: tuple[str, ...] = (),
) -> RollScenario:
    held = {"".join(symbol.upper().split()) for symbol in open_option_symbols}
    marked = replace(
        candidate,
        also_open="".join(candidate.option_symbol.upper().split()) in held,
    )
    return RollScenario(
        source_option_symbol=source.option_symbol,
        source_expiration=source.expires_on,
        source_strike=source.strike,
        source_contracts=source.contracts,
        target_expiration=marked.expires_on,
        target_strike=marked.strike,
        strike_lift_per_share=marked.strike_change_per_share,
        added_days=marked.added_days,
        net_roll_per_share=marked.net_roll_per_share,
        net_roll_cash=marked.net_roll_cash,
        assignment_room_gain=marked.assignment_room_gain,
        target_buffer_percent=marked.target_buffer_percent,
        quote_source=marked.quote_source,
        option_side=source.option_side,
        cost_label=marked.cost_label,
        family_label=marked.family_label,
        highlight=marked.highlight,
        also_open=marked.also_open,
        cash_per_extra_day=marked.cash_per_extra_day,
        theta_per_share=marked.theta_per_share,
    )
