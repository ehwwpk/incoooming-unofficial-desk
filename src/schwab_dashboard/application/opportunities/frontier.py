from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal

from schwab_dashboard.domain.opportunity import (
    RadarCandidate,
    RadarCandidateLabel,
    RadarMode,
)

_MAX_HORIZONS = 3
_MAX_PER_HORIZON = 3


def select_diversified_frontier(
    candidates: tuple[RadarCandidate, ...],
) -> tuple[RadarCandidate, ...]:
    """Select no more than nine IV-aware trade-offs across adaptive term cohorts."""

    selected: list[RadarCandidate] = []
    for horizon in _term_cohorts(candidates):
        selected.extend(_select_horizon(horizon))
    return tuple(selected)


def order_general_frontier(
    candidates: tuple[RadarCandidate, ...],
    *,
    mode: RadarMode,
) -> tuple[RadarCandidate, ...]:
    """Present the selected frontier by time, then increasing protection."""

    def strike_key(candidate: RadarCandidate) -> Decimal:
        return candidate.strike if mode is RadarMode.COVERED_CALL else -candidate.strike

    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                candidate.days_to_expiration,
                strike_key(candidate),
                candidate.spread_percent,
                -_liquidity(candidate),
                candidate.option_symbol,
            ),
        )
    )


def _term_cohorts(
    candidates: tuple[RadarCandidate, ...],
) -> tuple[tuple[RadarCandidate, ...], ...]:
    """Split the expirations actually returned into up to three contiguous cohorts.

    The old fixed 5-20 / 21-40 / 41-60 buckets silently discarded 61+ DTE
    contracts. Cohorts now adapt to the listed expirations while preserving near-
    to-far ordering and the existing three-comparisons-per-cohort density limit.
    """

    unique_dtes = sorted({candidate.days_to_expiration for candidate in candidates})
    if not unique_dtes:
        return ()
    cohort_count = min(_MAX_HORIZONS, len(unique_dtes))
    base_size, larger_cohorts = divmod(len(unique_dtes), cohort_count)
    cohorts: list[tuple[RadarCandidate, ...]] = []
    start = 0
    for index in range(cohort_count):
        size = base_size + (1 if index < larger_cohorts else 0)
        cohort_dtes = set(unique_dtes[start : start + size])
        cohorts.append(
            tuple(
                candidate
                for candidate in candidates
                if candidate.days_to_expiration in cohort_dtes
            )
        )
        start += size
    return tuple(cohorts)


def _select_horizon(candidates: tuple[RadarCandidate, ...]) -> tuple[RadarCandidate, ...]:
    if not candidates:
        return ()
    if len(candidates) == 1:
        return (replace(candidates[0], label=RadarCandidateLabel.BALANCED),)

    remaining = list(candidates)
    credit = _take_best(remaining, key=_credit_key, used_expirations=set())
    room = _take_best(
        remaining,
        key=_room_key,
        used_expirations={credit.expiration_date},
    )

    if not remaining:
        return (
            replace(credit, label=RadarCandidateLabel.MORE_CREDIT),
            replace(room, label=RadarCandidateLabel.MORE_ROOM),
        )

    balanced = _take_best(
        remaining,
        key=lambda candidate: _balanced_key(candidate, candidates),
        used_expirations={credit.expiration_date, room.expiration_date},
    )
    chosen = (
        replace(credit, label=RadarCandidateLabel.MORE_CREDIT),
        replace(balanced, label=RadarCandidateLabel.BALANCED),
        replace(room, label=RadarCandidateLabel.MORE_ROOM),
    )
    return chosen[:_MAX_PER_HORIZON]


def _take_best(
    remaining: list[RadarCandidate],
    *,
    key: Callable[[RadarCandidate], tuple[object, ...]],
    used_expirations: set[object],
) -> RadarCandidate:
    candidate = max(
        remaining,
        key=lambda item: (
            item.clears_all_rules,
            item.expiration_date not in used_expirations,
            *key(item),
            item.option_symbol,
        ),
    )
    remaining.remove(candidate)
    return candidate


def _credit_key(candidate: RadarCandidate) -> tuple[object, ...]:
    return (
        candidate.simple_annualized_rate_percent,
        candidate.bid_credit_per_calendar_day,
        _protection(candidate),
        -candidate.spread_percent,
        _liquidity(candidate),
        -candidate.days_to_expiration,
    )


def _room_key(candidate: RadarCandidate) -> tuple[object, ...]:
    return (
        _protection(candidate),
        candidate.simple_annualized_rate_percent,
        -candidate.spread_percent,
        _liquidity(candidate),
        -candidate.days_to_expiration,
    )


def _balanced_key(
    candidate: RadarCandidate,
    horizon: tuple[RadarCandidate, ...],
) -> tuple[object, ...]:
    rate = _normalize(
        candidate.simple_annualized_rate_percent,
        tuple(item.simple_annualized_rate_percent for item in horizon),
    )
    protection = _normalize(
        _protection(candidate),
        tuple(_protection(item) for item in horizon),
    )
    execution = Decimal("1") - _normalize(
        candidate.spread_percent,
        tuple(item.spread_percent for item in horizon),
    )
    liquidity = _normalize(
        _liquidity(candidate),
        tuple(_liquidity(item) for item in horizon),
    )
    score = (
        rate * Decimal("0.38")
        + protection * Decimal("0.38")
        + execution * Decimal("0.18")
        + liquidity * Decimal("0.06")
    )
    return (
        score,
        -candidate.spread_percent,
        candidate.simple_annualized_rate_percent,
        _protection(candidate),
        -candidate.days_to_expiration,
    )


def _protection(candidate: RadarCandidate) -> Decimal:
    if candidate.strike_distance_in_moves is not None:
        return candidate.strike_distance_in_moves
    return candidate.room_percent / Decimal("100")


def _liquidity(candidate: RadarCandidate) -> Decimal:
    return Decimal((candidate.open_interest or 0) + (candidate.volume or 0))


def _normalize(value: Decimal, values: tuple[Decimal, ...]) -> Decimal:
    minimum = min(values)
    maximum = max(values)
    if maximum == minimum:
        return Decimal("0.5")
    return (value - minimum) / (maximum - minimum)
