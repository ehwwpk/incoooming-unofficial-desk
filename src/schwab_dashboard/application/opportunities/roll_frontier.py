from __future__ import annotations

from dataclasses import replace

from schwab_dashboard.application.rolls import RollQuote, RollSource, select_roll_candidates
from schwab_dashboard.domain.opportunity import (
    RadarCandidate,
    RadarCandidateLabel,
    RadarRollSelectionContext,
)

_MAX_ROLL_CHOICES = 9


def select_roll_frontier(
    candidates: tuple[RadarCandidate, ...],
    *,
    context: RadarRollSelectionContext,
    preferred: RadarCandidate | None = None,
) -> tuple[RadarCandidate, ...]:
    """Use the same nearby listed roll grid as Nibwick and Roll Board."""

    by_symbol = {candidate.option_symbol: candidate for candidate in candidates}
    if preferred is not None:
        by_symbol[preferred.option_symbol] = preferred
    source = RollSource(
        symbol="",
        option_symbol="",
        option_side=context.option_side,
        expires_on=context.source_expiration_date,
        strike=context.source_strike,
        contracts=1,
        close_ask_per_share=context.source_close_ask_per_share,
        current_price=context.source_current_price,
        quote_status="RADAR",
    )
    result = select_roll_candidates(
        source,
        tuple(
            RollQuote(
                option_symbol=candidate.option_symbol,
                expires_on=candidate.expiration_date,
                strike=candidate.strike,
                sell_bid_per_share=candidate.bid,
                quote_source="RADAR CHAIN BID",
                spread_percent=candidate.spread_percent,
                open_interest=candidate.open_interest,
                volume=candidate.volume,
                theta_per_share=candidate.theta,
            )
            for candidate in by_symbol.values()
        ),
        limit=_MAX_ROLL_CHOICES,
        preferred_option_symbol=(preferred.option_symbol if preferred is not None else None),
    )
    labels = {
        "NEAR FLAT": RadarCandidateLabel.NEAR_FLAT,
        "NET CREDIT": RadarCandidateLabel.NET_CREDIT,
        "DEBIT FOR ROOM": RadarCandidateLabel.DEBIT_FOR_ROOM,
    }
    return tuple(
        replace(by_symbol[item.option_symbol], label=labels[item.cost_label])
        for item in result.candidates
        if item.option_symbol in by_symbol
    )
