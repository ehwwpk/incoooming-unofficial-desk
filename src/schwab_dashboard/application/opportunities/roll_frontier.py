from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from schwab_dashboard.domain.opportunity import (
    RadarCandidate,
    RadarCandidateLabel,
    RadarRollSelectionContext,
)

_MAX_ROLL_CHOICES = 9
_NEAR_FLAT_PER_SHARE = Decimal("0.10")
_SMALL_MOVE_PER_SHARE = Decimal("0.25")
_MODERATE_MOVE_PER_SHARE = Decimal("0.50")
_ONE_DOLLAR_PER_SHARE = Decimal("1.00")


def select_roll_frontier(
    candidates: tuple[RadarCandidate, ...],
    *,
    context: RadarRollSelectionContext,
    preferred: RadarCandidate | None = None,
) -> tuple[RadarCandidate, ...]:
    """Rank later, higher calls by two-leg roll economics.

    Near-flat replacements lead. Within the same cost band, fewer added days,
    greater strike improvement, and cleaner markets break ties. The explicitly
    linked Nibwick target remains visible but is placed at its economic rank.
    """

    eligible = {
        candidate.option_symbol: candidate
        for candidate in candidates
        if _is_roll_up_and_out(candidate, context=context)
    }
    if preferred is not None and _is_roll_up_and_out(preferred, context=context):
        eligible[preferred.option_symbol] = preferred

    ordered = sorted(
        eligible.values(),
        key=lambda candidate: _roll_rank_key(candidate, context=context),
    )
    selected = ordered[:_MAX_ROLL_CHOICES]
    if (
        preferred is not None
        and preferred.option_symbol in eligible
        and all(item.option_symbol != preferred.option_symbol for item in selected)
    ):
        if selected:
            selected[-1] = preferred
        else:
            selected.append(preferred)
        selected.sort(key=lambda candidate: _roll_rank_key(candidate, context=context))

    return tuple(_with_roll_label(candidate, context=context) for candidate in selected)


def _is_roll_up_and_out(
    candidate: RadarCandidate,
    *,
    context: RadarRollSelectionContext,
) -> bool:
    return (
        candidate.expiration_date > context.source_expiration_date
        and candidate.strike > context.source_strike
    )


def _roll_rank_key(
    candidate: RadarCandidate,
    *,
    context: RadarRollSelectionContext,
) -> tuple[object, ...]:
    net = candidate.bid - context.source_close_ask_per_share
    added_days = (candidate.expiration_date - context.source_expiration_date).days
    strike_lift = candidate.strike - context.source_strike
    liquidity = Decimal((candidate.open_interest or 0) + (candidate.volume or 0))
    return (
        _cost_band(net),
        abs(net),
        net < 0,
        added_days,
        -strike_lift,
        candidate.spread_percent,
        -liquidity,
        candidate.expiration_date,
        candidate.strike,
        candidate.option_symbol,
    )


def _cost_band(net_per_share: Decimal) -> int:
    absolute = abs(net_per_share)
    if absolute <= _NEAR_FLAT_PER_SHARE:
        return 0
    if absolute <= _SMALL_MOVE_PER_SHARE:
        return 1
    if absolute <= _MODERATE_MOVE_PER_SHARE:
        return 2
    if absolute <= _ONE_DOLLAR_PER_SHARE:
        return 3
    return 4


def _with_roll_label(
    candidate: RadarCandidate,
    *,
    context: RadarRollSelectionContext,
) -> RadarCandidate:
    net = candidate.bid - context.source_close_ask_per_share
    if abs(net) <= _NEAR_FLAT_PER_SHARE:
        label = RadarCandidateLabel.NEAR_FLAT
    elif net > 0:
        label = RadarCandidateLabel.NET_CREDIT
    else:
        label = RadarCandidateLabel.DEBIT_FOR_ROOM
    return replace(candidate, label=label)
