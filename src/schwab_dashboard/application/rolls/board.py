from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from schwab_dashboard.application.dashboard.anchors import option_contract_anchor
from schwab_dashboard.application.dashboard.covered_calls import OpenCallClock
from schwab_dashboard.application.dashboard.models import DashboardSnapshot, LiveOpenOptionPosition
from schwab_dashboard.application.rolls import RollQuote, RollSource, select_roll_candidates
from schwab_dashboard.application.rolls.models import RollCandidate
from schwab_dashboard.domain.instruments import OptionSide

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class RollBoardRow:
    anchor_id: str
    symbol: str
    source: RollSource
    days_to_expiration: int
    urgency: str
    urgency_rank: int
    strike_distance_per_share: Decimal
    strike_distance_percent: Decimal
    assignment_notional: Decimal
    candidates: tuple[RollCandidate, ...]
    no_clean_reason: str | None


@dataclass(frozen=True, slots=True)
class RollBoardProjection:
    rows: tuple[RollBoardRow, ...]
    total_contracts: int
    attention_count: int
    clean_roll_count: int
    no_clean_count: int
    total_assignment_notional: Decimal
    posture: str


def build_roll_board(snapshot: DashboardSnapshot) -> RollBoardProjection:
    rows: list[RollBoardRow] = []
    for underlying in snapshot.underlyings:
        for call in underlying.open_call_clocks:
            row = _call_row(underlying.symbol, underlying.current_price, call)
            if row is not None:
                rows.append(row)
    if snapshot.live_position_book is not None:
        for put in snapshot.live_position_book.puts:
            row = _put_row(put)
            if row is not None:
                rows.append(row)
    rows.sort(
        key=lambda row: (
            row.urgency_rank,
            row.source.expires_on,
            abs(row.strike_distance_percent),
            row.symbol,
            row.source.strike,
        )
    )
    attention_count = sum(row.urgency_rank == 0 for row in rows)
    no_clean_count = sum(not row.candidates for row in rows)
    posture = (
        "DATA FOG"
        if rows and no_clean_count == len(rows)
        else "AT THE DESK"
        if attention_count
        else "WATCHING"
        if rows
        else "PATROL"
    )
    return RollBoardProjection(
        rows=tuple(rows),
        total_contracts=sum((row.source.contracts for row in rows), 0),
        attention_count=attention_count,
        clean_roll_count=len(rows) - no_clean_count,
        no_clean_count=no_clean_count,
        total_assignment_notional=sum(
            (row.assignment_notional for row in rows),
            ZERO,
        ),
        posture=posture,
    )


def _call_row(
    symbol: str,
    current_price: Decimal,
    call: OpenCallClock,
) -> RollBoardRow | None:
    if not call.can_close_or_roll:
        return None
    urgency = _urgency(call.strike_distance_percent, call.days_to_expiration)
    if urgency is None:
        return None
    source = RollSource(
        symbol=symbol,
        option_symbol=call.record_id,
        option_side=OptionSide.CALL,
        expires_on=call.expires_on,
        strike=call.strike,
        contracts=call.contracts,
        close_ask_per_share=call.close_ask_per_share,
        current_price=current_price,
        quote_status=call.quote_status,
    )
    result = select_roll_candidates(
        source,
        tuple(
            RollQuote(
                option_symbol=quote.option_symbol,
                expires_on=quote.expires_on,
                strike=quote.strike,
                sell_bid_per_share=quote.sell_bid_per_share,
                quote_source=quote.quote_source,
                spread_percent=quote.spread_percent,
                open_interest=quote.open_interest,
                volume=quote.volume,
            )
            for quote in call.roll_quote_candidates
        ),
    )
    return RollBoardRow(
        anchor_id=f"roll-{option_contract_anchor(call.record_id)}",
        symbol=symbol,
        source=source,
        days_to_expiration=call.days_to_expiration,
        urgency=urgency[0],
        urgency_rank=urgency[1],
        strike_distance_per_share=call.strike_distance_per_share,
        strike_distance_percent=call.strike_distance_percent,
        assignment_notional=call.strike * Decimal(call.contracts * 100),
        candidates=result.candidates,
        no_clean_reason=result.no_clean_reason,
    )


def _put_row(put: LiveOpenOptionPosition) -> RollBoardRow | None:
    if (
        not put.can_close_or_roll
        or put.strike_distance_percent is None
        or put.strike_distance_per_share is None
    ):
        return None
    urgency = _urgency(put.strike_distance_percent, put.days_to_expiration)
    if urgency is None:
        return None
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
    result = select_roll_candidates(source, put.roll_quote_candidates)
    return RollBoardRow(
        anchor_id=f"roll-{option_contract_anchor(put.option_symbol)}",
        symbol=put.underlying_symbol,
        source=source,
        days_to_expiration=put.days_to_expiration,
        urgency=urgency[0],
        urgency_rank=urgency[1],
        strike_distance_per_share=put.strike_distance_per_share,
        strike_distance_percent=put.strike_distance_percent,
        assignment_notional=put.strike * put.contract_multiplier * Decimal(put.contracts),
        candidates=result.candidates,
        no_clean_reason=result.no_clean_reason,
    )


def _urgency(distance_percent: Decimal, dte: int) -> tuple[str, int] | None:
    if distance_percent <= ZERO and dte <= 30:
        return ("NEEDS ATTENTION", 0)
    if distance_percent <= Decimal("3") and dte <= 21:
        return ("WORTH CHECKING", 1)
    if distance_percent <= Decimal("7") and dte <= 7:
        return ("KEEP AN EYE ON THIS", 2)
    return None
