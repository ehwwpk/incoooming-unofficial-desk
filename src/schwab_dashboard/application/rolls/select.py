from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from decimal import Decimal

from schwab_dashboard.application.rolls.models import (
    RollCandidate,
    RollQuote,
    RollSearchResult,
    RollSource,
)
from schwab_dashboard.domain.instruments import OptionSide

ZERO = Decimal("0")
HUNDRED = Decimal("100")
NEAR_FLAT = Decimal("0.10")
SMALL_CASH_MOVE = Decimal("0.25")
MODERATE_CASH_MOVE = Decimal("0.50")


def select_roll_candidates(
    source: RollSource,
    quotes: Sequence[RollQuote],
    *,
    limit: int = 9,
) -> RollSearchResult:
    """Build a compact, diversified roll frontier from conservative quote math.

    The open short is bought at its ask and a replacement is sold at its bid.
    Calls may move out at the same strike or up and out. Puts may move out at
    the same strike or down and out. A call roll-down is intentionally excluded.
    """

    if limit < 1:
        raise ValueError("limit must be positive")
    if source.close_ask_per_share <= ZERO:
        return RollSearchResult(
            source=source,
            candidates=(),
            examined_quotes=len(quotes),
            eligible_quotes=0,
            no_clean_reason=(
                "The current buy-to-close ask is unavailable, so roll cash cannot be "
                "checked honestly."
            ),
        )

    eligible = tuple(
        _candidate(source, quote)
        for quote in quotes
        if _is_directionally_valid(source, quote)
    )
    if not eligible:
        return RollSearchResult(
            source=source,
            candidates=(),
            examined_quotes=len(quotes),
            eligible_quotes=0,
            no_clean_reason=_empty_reason(source, quotes),
        )

    ordered = sorted(eligible, key=_primary_rank)
    selected = _diversified_frontier(ordered, limit=limit)
    return RollSearchResult(
        source=source,
        candidates=selected,
        examined_quotes=len(quotes),
        eligible_quotes=len(eligible),
    )


def _candidate(source: RollSource, quote: RollQuote) -> RollCandidate:
    net = quote.sell_bid_per_share - source.close_ask_per_share
    strike_change = quote.strike - source.strike
    direction = Decimal("1") if source.option_side is OptionSide.CALL else Decimal("-1")
    covered_units = Decimal(source.contracts) * source.contract_multiplier
    room_gain = strike_change * direction * covered_units
    buffer = (
        (quote.strike - source.current_price) / source.current_price * HUNDRED
        if source.option_side is OptionSide.CALL and source.current_price > ZERO
        else (source.current_price - quote.strike) / source.current_price * HUNDRED
        if source.current_price > ZERO
        else ZERO
    )
    return RollCandidate(
        option_symbol=quote.option_symbol,
        option_side=source.option_side,
        expires_on=quote.expires_on,
        strike=quote.strike,
        sell_bid_per_share=quote.sell_bid_per_share,
        net_roll_per_share=net,
        net_roll_cash=net * covered_units,
        strike_change_per_share=strike_change,
        added_days=(quote.expires_on - source.expires_on).days,
        assignment_room_gain=room_gain,
        target_buffer_percent=buffer.quantize(Decimal("0.1")),
        cost_label=_cost_label(net),
        family_label="",
        quote_source=quote.quote_source,
        spread_percent=quote.spread_percent,
        open_interest=quote.open_interest,
        volume=quote.volume,
    )


def _is_directionally_valid(source: RollSource, quote: RollQuote) -> bool:
    if quote.expires_on <= source.expires_on or quote.sell_bid_per_share <= ZERO:
        return False
    if source.option_side is OptionSide.CALL:
        return quote.strike >= source.strike
    return quote.strike <= source.strike


def _primary_rank(candidate: RollCandidate) -> tuple[object, ...]:
    liquidity = (candidate.open_interest or 0) + (candidate.volume or 0)
    return (
        _cost_band(candidate.net_roll_per_share),
        abs(candidate.net_roll_per_share),
        candidate.net_roll_per_share < ZERO,
        candidate.added_days,
        -candidate.assignment_room_gain,
        candidate.spread_percent if candidate.spread_percent is not None else Decimal("999"),
        -liquidity,
        candidate.expires_on,
        candidate.strike,
        candidate.option_symbol,
    )


def _diversified_frontier(
    ordered: Sequence[RollCandidate],
    *,
    limit: int,
) -> tuple[RollCandidate, ...]:
    families = (
        ("LOWEST CASH COST", sorted(ordered, key=_primary_rank)),
        (
            "LEAST EXTRA TIME",
            sorted(
                ordered,
                key=lambda item: (
                    item.added_days,
                    _cost_band(item.net_roll_per_share),
                    abs(item.net_roll_per_share),
                    -item.assignment_room_gain,
                ),
            ),
        ),
        (
            "MOST STRIKE ROOM",
            sorted(
                ordered,
                key=lambda item: (
                    -item.assignment_room_gain,
                    _cost_band(item.net_roll_per_share),
                    item.added_days,
                    abs(item.net_roll_per_share),
                ),
            ),
        ),
    )
    selected: list[RollCandidate] = []
    used: set[str] = set()
    for label, family in families:
        candidate = next((item for item in family if _key(item) not in used), None)
        if candidate is None:
            continue
        selected.append(replace(candidate, family_label=label))
        used.add(_key(candidate))
        if len(selected) == limit:
            return tuple(sorted(selected, key=_primary_rank))
    for rank in range(len(ordered)):
        for label, family in families:
            if rank >= len(family):
                continue
            candidate = family[rank]
            key = _key(candidate)
            if key in used:
                continue
            selected.append(replace(candidate, family_label=label))
            used.add(key)
            if len(selected) == limit:
                return tuple(sorted(selected, key=_primary_rank))
    return tuple(sorted(selected, key=_primary_rank))


def _key(candidate: RollCandidate) -> str:
    return candidate.option_symbol or f"{candidate.expires_on.isoformat()}:{candidate.strike}"


def _cost_band(value: Decimal) -> int:
    absolute = abs(value)
    if absolute <= NEAR_FLAT:
        return 0
    if absolute <= SMALL_CASH_MOVE:
        return 1
    if absolute <= MODERATE_CASH_MOVE:
        return 2
    return 3


def _cost_label(value: Decimal) -> str:
    if abs(value) <= NEAR_FLAT:
        return "NEAR FLAT"
    if value > ZERO:
        return "NET CREDIT"
    return "DEBIT FOR ROOM"


def _empty_reason(source: RollSource, quotes: Sequence[RollQuote]) -> str:
    if not quotes:
        return "No replacement quotes are available for this contract yet."
    if not any(quote.expires_on > source.expires_on for quote in quotes):
        return "The chain has no later expiration in the loaded range."
    direction = "same or higher" if source.option_side is OptionSide.CALL else "same or lower"
    return f"Later contracts loaded, but none has a positive bid at a {direction} strike."
