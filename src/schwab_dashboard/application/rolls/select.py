from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import date
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
NEARBY_LISTED_EXPIRIES = 3
NEARBY_LISTED_STRIKES = 3
MAX_NEARBY_EXTRA_DAYS = 28
MAX_NEARBY_STRIKE_PERCENT = Decimal("8")
NEAREST_CASH_AND_TIME = "NEAREST CASH AND TIME"


def select_roll_candidates(
    source: RollSource,
    quotes: Sequence[RollQuote],
    *,
    limit: int = 9,
    preferred_option_symbol: str | None = None,
) -> RollSearchResult:
    """Build a nearby listed roll grid from conservative two-leg quote math.

    The open short is bought at its ask and a replacement is sold at its bid.
    Calls must move up and out: a later expiration and a strictly higher strike.
    Puts may move out at the same strike or down and out. The default ladder is
    the next three listed expiries and the next three listed strikes in the
    protective direction, limited to about 8% of the source strike and 28 extra
    days. Far-dated and far-strike contracts are excluded.
    """

    if limit < 1:
        raise ValueError("limit must be positive")
    if source.deliverable_shares_per_contract is None:
        return RollSearchResult(
            source=source,
            candidates=(),
            examined_quotes=len(quotes),
            eligible_quotes=0,
            no_clean_reason=(
                "The source contract has an adjusted or unresolved deliverable, so comparable "
                "roll economics are unavailable."
            ),
        )
    if source.close_ask_per_share <= ZERO:
        return RollSearchResult(
            source=source,
            candidates=(),
            examined_quotes=len(quotes),
            eligible_quotes=0,
            no_clean_reason=(
                "The current buy-to-close ask is unavailable, so roll cash cannot be calculated."
            ),
        )

    eligible = tuple(
        _candidate(source, quote) for quote in quotes if _is_directionally_valid(source, quote)
    )
    if not eligible:
        return RollSearchResult(
            source=source,
            candidates=(),
            examined_quotes=len(quotes),
            eligible_quotes=0,
            no_clean_reason=_empty_reason(source, quotes),
        )
    nearby_eligible = tuple(item for item in eligible if _is_nearby(item, source))
    if not nearby_eligible:
        return RollSearchResult(
            source=source,
            candidates=(),
            examined_quotes=len(quotes),
            eligible_quotes=len(eligible),
            no_clean_reason=(
                "Later contracts loaded, but none is a small strike move inside a few extra weeks."
            ),
        )

    neighborhood = _nearby_frontier(nearby_eligible, source.option_side, limit=limit)
    selected = list(neighborhood)
    preferred_key = _canonical(preferred_option_symbol or "")
    if preferred_key:
        extra = next(
            (item for item in eligible if _canonical(item.option_symbol) == preferred_key),
            None,
        )
        if extra is not None and all(_key(item) != _key(extra) for item in selected):
            selected.append(extra)

    highlighted = min(selected, key=_dual_best_rank) if selected else None
    labeled = tuple(
        replace(
            item,
            highlight=highlighted is not None and _key(item) == _key(highlighted),
            family_label=(
                NEAREST_CASH_AND_TIME
                if highlighted is not None and _key(item) == _key(highlighted)
                else ""
            ),
        )
        for item in sorted(selected, key=lambda item: _display_rank(item, source.option_side))
    )
    return RollSearchResult(
        source=source,
        candidates=labeled,
        examined_quotes=len(quotes),
        eligible_quotes=len(eligible),
    )


def _candidate(source: RollSource, quote: RollQuote) -> RollCandidate:
    net = quote.sell_bid_per_share - source.close_ask_per_share
    strike_change = quote.strike - source.strike
    direction = Decimal("1") if source.option_side is OptionSide.CALL else Decimal("-1")
    premium_units = Decimal(source.contracts) * source.contract_multiplier
    deliverable_units = (
        Decimal(source.contracts) * source.deliverable_shares_per_contract
        if source.deliverable_shares_per_contract is not None
        else ZERO
    )
    room_gain = strike_change * direction * deliverable_units
    added_days = (quote.expires_on - source.expires_on).days
    buffer = (
        (quote.strike - source.current_price) / source.current_price * HUNDRED
        if source.option_side is OptionSide.CALL and source.current_price > ZERO
        else (source.current_price - quote.strike) / source.current_price * HUNDRED
        if source.current_price > ZERO
        else ZERO
    )
    cash = net * premium_units
    return RollCandidate(
        option_symbol=quote.option_symbol,
        option_side=source.option_side,
        expires_on=quote.expires_on,
        strike=quote.strike,
        sell_bid_per_share=quote.sell_bid_per_share,
        net_roll_per_share=net,
        net_roll_cash=cash,
        strike_change_per_share=strike_change,
        added_days=added_days,
        assignment_room_gain=room_gain,
        target_buffer_percent=buffer.quantize(Decimal("0.1")),
        cost_label=_cost_label(net),
        family_label="",
        quote_source=quote.quote_source,
        spread_percent=quote.spread_percent,
        open_interest=quote.open_interest,
        volume=quote.volume,
        cash_per_extra_day=(
            (cash / Decimal(added_days)).quantize(Decimal("0.01")) if added_days else None
        ),
        theta_per_share=quote.theta_per_share,
    )


def _is_directionally_valid(source: RollSource, quote: RollQuote) -> bool:
    if quote.expires_on <= source.expires_on or quote.sell_bid_per_share <= ZERO:
        return False
    if source.option_side == OptionSide.CALL:
        return quote.strike > source.strike
    return quote.strike <= source.strike


def _is_nearby(candidate: RollCandidate, source: RollSource) -> bool:
    if candidate.added_days > MAX_NEARBY_EXTRA_DAYS:
        return False
    if source.strike <= ZERO:
        return True
    move = abs(candidate.strike - source.strike) / source.strike * HUNDRED
    return move <= MAX_NEARBY_STRIKE_PERCENT


def _nearby_frontier(
    eligible: Sequence[RollCandidate],
    option_side: OptionSide,
    *,
    limit: int,
) -> tuple[RollCandidate, ...]:
    by_expiry: dict[date, list[RollCandidate]] = {}
    for candidate in eligible:
        by_expiry.setdefault(candidate.expires_on, []).append(candidate)
    selected: list[RollCandidate] = []
    for expiry in sorted(by_expiry)[:NEARBY_LISTED_EXPIRIES]:
        selected.extend(_nearby_strikes(by_expiry[expiry], option_side))
        if len(selected) >= limit:
            return tuple(selected[:limit])
    return tuple(selected[:limit])


def _nearby_strikes(
    candidates: Sequence[RollCandidate],
    option_side: OptionSide,
) -> tuple[RollCandidate, ...]:
    by_strike: dict[Decimal, list[RollCandidate]] = {}
    for candidate in candidates:
        by_strike.setdefault(candidate.strike, []).append(candidate)
    ordered_strikes = sorted(
        by_strike,
        reverse=option_side is OptionSide.PUT,
    )
    chosen: list[RollCandidate] = []
    for strike in ordered_strikes[:NEARBY_LISTED_STRIKES]:
        chosen.append(min(by_strike[strike], key=_dual_best_rank))
    return tuple(chosen)


def _display_rank(candidate: RollCandidate, option_side: OptionSide) -> tuple[object, ...]:
    strike_order = -candidate.strike if option_side is OptionSide.PUT else candidate.strike
    return (candidate.expires_on, strike_order, candidate.option_symbol)


def _dual_best_rank(candidate: RollCandidate) -> tuple[object, ...]:
    liquidity = (candidate.open_interest or 0) + (candidate.volume or 0)
    return (
        _cost_band(candidate.net_roll_per_share),
        candidate.added_days,
        abs(candidate.net_roll_per_share),
        candidate.net_roll_per_share < ZERO,
        abs(candidate.strike_change_per_share),
        candidate.spread_percent if candidate.spread_percent is not None else Decimal("999"),
        -liquidity,
        candidate.option_symbol,
    )


def _key(candidate: RollCandidate) -> str:
    return candidate.option_symbol or f"{candidate.expires_on.isoformat()}:{candidate.strike}"


def _canonical(value: str) -> str:
    return "".join(value.upper().split())


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
    direction = "higher" if source.option_side is OptionSide.CALL else "same or lower"
    return f"Later contracts loaded, but none has a positive bid at a {direction} strike."
