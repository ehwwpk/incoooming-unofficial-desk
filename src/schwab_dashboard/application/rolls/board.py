from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from schwab_dashboard.application.dashboard.anchors import option_contract_anchor
from schwab_dashboard.application.dashboard.covered_calls import OpenCallClock
from schwab_dashboard.application.dashboard.models import DashboardSnapshot, LiveOpenOptionPosition
from schwab_dashboard.application.rolls import RollQuote, RollSource, select_roll_candidates
from schwab_dashboard.application.rolls.models import RollCandidate
from schwab_dashboard.application.values import sum_if_complete
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
    assignment_notional: Decimal | None
    candidates: tuple[RollCandidate, ...]
    no_clean_reason: str | None


@dataclass(frozen=True, slots=True)
class RollBoardProjection:
    rows: tuple[RollBoardRow, ...]
    total_contracts: int
    attention_count: int
    clean_roll_count: int
    no_clean_count: int
    total_assignment_notional: Decimal | None
    posture: str


def build_roll_board(snapshot: DashboardSnapshot) -> RollBoardProjection:
    open_symbols = _open_option_symbols(snapshot)
    rows: list[RollBoardRow] = []
    for underlying in snapshot.underlyings:
        for call in underlying.open_call_clocks:
            row = _call_row(
                underlying.symbol,
                underlying.current_price,
                call,
                open_symbols=open_symbols,
            )
            if row is not None:
                rows.append(row)
    if snapshot.live_position_book is not None:
        for put in snapshot.live_position_book.puts:
            row = _put_row(put, open_symbols=open_symbols)
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
        total_assignment_notional=sum_if_complete(row.assignment_notional for row in rows),
        posture=posture,
    )


def _call_row(
    symbol: str,
    current_price: Decimal,
    call: OpenCallClock,
    *,
    open_symbols: frozenset[str],
) -> RollBoardRow | None:
    if (
        not call.can_close_or_roll
        or call.strike_distance_percent is None
        or call.strike_distance_per_share is None
    ):
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
        close_ask_per_share=call.close_ask_per_share or ZERO,
        current_price=current_price,
        quote_status=call.quote_status,
        contract_multiplier=call.contract_multiplier,
        deliverable_shares_per_contract=call.deliverable_shares_per_contract,
        account_mask=call.account_mask,
        account_id=call.account_id,
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
                theta_per_share=quote.theta_per_share,
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
        assignment_notional=(
            call.strike * call.obligated_shares if call.obligated_shares is not None else None
        ),
        candidates=_mark_also_open(result.candidates, open_symbols),
        no_clean_reason=result.no_clean_reason,
    )


def _put_row(
    put: LiveOpenOptionPosition,
    *,
    open_symbols: frozenset[str],
) -> RollBoardRow | None:
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
        deliverable_shares_per_contract=put.deliverable_shares_per_contract,
        account_mask=put.account_mask,
        account_id=put.account_id,
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
        assignment_notional=(
            put.strike * put.obligated_shares if put.obligated_shares is not None else None
        ),
        candidates=_mark_also_open(result.candidates, open_symbols),
        no_clean_reason=result.no_clean_reason,
    )


def _open_option_symbols(snapshot: DashboardSnapshot) -> frozenset[str]:
    symbols: set[str] = set()
    for underlying in snapshot.underlyings:
        for call in underlying.open_call_clocks:
            if call.can_close_or_roll:
                symbols.add(_canonical(call.record_id))
    if snapshot.live_position_book is not None:
        for option in (*snapshot.live_position_book.calls, *snapshot.live_position_book.puts):
            if option.can_close_or_roll:
                symbols.add(_canonical(option.option_symbol))
    return frozenset(symbols)


def _mark_also_open(
    candidates: tuple[RollCandidate, ...],
    open_symbols: frozenset[str],
) -> tuple[RollCandidate, ...]:
    return tuple(
        replace(candidate, also_open=_canonical(candidate.option_symbol) in open_symbols)
        for candidate in candidates
    )


def _canonical(value: str) -> str:
    return "".join(value.upper().split())


def _urgency(distance_percent: Decimal, dte: int) -> tuple[str, int] | None:
    if distance_percent <= ZERO and dte <= 30:
        return ("NEEDS ATTENTION", 0)
    if distance_percent <= Decimal("3") and dte <= 21:
        return ("WORTH CHECKING", 1)
    if distance_percent <= Decimal("7") and dte <= 7:
        return ("KEEP AN EYE ON THIS", 2)
    return None
