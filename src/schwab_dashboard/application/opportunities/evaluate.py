from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.opportunities.eligibility import evaluate_gates, passes
from schwab_dashboard.application.opportunities.expiration_map import build_expiration_map
from schwab_dashboard.application.opportunities.frontier import (
    order_general_frontier,
    select_diversified_frontier,
)
from schwab_dashboard.application.opportunities.market_context import range_position, session_return
from schwab_dashboard.application.opportunities.quote_math import (
    bid_credit_per_calendar_day,
    days_to_expiration,
    expected_move,
    midpoint,
    simple_annualized_rate,
    spread_percent,
)
from schwab_dashboard.application.opportunities.roll_frontier import select_roll_frontier
from schwab_dashboard.domain.opportunity import (
    RadarAccountContext,
    RadarCandidate,
    RadarMarketBundle,
    RadarMarketContract,
    RadarMode,
    RadarPolicy,
    RadarProjection,
    RadarRollSelectionContext,
    RadarState,
)

_PLANNING_GATE_CODES = frozenset(
    {
        "covered_lots",
        "reserved_cash",
        "fast_move",
    }
)


def evaluate_radar(
    *,
    lookup_id: str | None,
    bundle: RadarMarketBundle,
    mode: RadarMode,
    account: RadarAccountContext,
    policy: RadarPolicy,
    now: datetime | None = None,
    preferred_strike: Decimal | None = None,
    preferred_expiration: date | None = None,
    roll_selection: RadarRollSelectionContext | None = None,
) -> RadarProjection:
    evaluated_at = now or datetime.now(UTC)
    spot = bundle.underlying_price
    five_day = session_return(bundle.daily_bars, 5)
    twenty_day = session_return(bundle.daily_bars, 20)
    position = range_position(bundle.daily_bars)
    warnings = list(bundle.warnings)
    if spot is None or spot <= 0:
        return _empty_projection(
            lookup_id=lookup_id,
            bundle=bundle,
            mode=mode,
            account=account,
            policy=policy,
            state=RadarState.PARTIAL,
            headline="A reliable stock price is unavailable",
            reasons=("Radar will not compare strikes without a positive underlying price.",),
            warnings=tuple(warnings),
            five_day=five_day,
            twenty_day=twenty_day,
            range_position_percent=position,
        )

    atm_iv = _atm_iv_by_expiration(bundle.contracts, spot=spot, mode=mode)
    comparisons: list[RadarCandidate] = []
    preferred_candidate: RadarCandidate | None = None
    rejected = 0
    for contract in bundle.contracts:
        if contract.option_side is not mode.option_side:
            continue
        candidate = _candidate(
            contract,
            spot=spot,
            mode=mode,
            account=account,
            policy=policy,
            five_day_move_percent=five_day,
            now=evaluated_at,
            atm_iv=atm_iv.get(contract.expiration_date),
        )
        if (
            preferred_strike is not None
            and preferred_expiration is not None
            and contract.strike == preferred_strike
            and contract.expiration_date == preferred_expiration
        ):
            preferred_candidate = candidate
        if (
            _passes_roll_research_gates(candidate)
            if roll_selection is not None
            else _passes_research_gates(candidate)
        ):
            comparisons.append(candidate)
        else:
            rejected += 1

    if roll_selection is not None:
        selected = select_roll_frontier(
            tuple(comparisons),
            context=roll_selection,
            preferred=preferred_candidate,
        )
    else:
        selected = _include_preferred_candidate(
            order_general_frontier(
                select_diversified_frontier(tuple(comparisons)),
                mode=mode,
            ),
            preferred_candidate,
        )
    if not selected:
        side_contract_count = sum(
            contract.option_side is mode.option_side for contract in bundle.contracts
        )
        reasons = _wait_reasons(
            mode=mode,
            account=account,
            policy=policy,
            contracts=tuple(bundle.contracts),
            five_day=five_day,
            rejected=rejected,
            for_roll=roll_selection is not None,
        )
        return _empty_projection(
            lookup_id=lookup_id,
            bundle=bundle,
            mode=mode,
            account=account,
            policy=policy,
            state=RadarState.WAIT,
            headline=_empty_headline(
                bundle.symbol,
                mode=mode,
                side_contract_count=side_contract_count,
                for_roll=roll_selection is not None,
            ),
            reasons=reasons,
            warnings=tuple(warnings),
            rejected_count=rejected,
            five_day=five_day,
            twenty_day=twenty_day,
            range_position_percent=position,
        )

    if any(item.expected_move is None for item in selected):
        warnings.append("Expected-move context is unavailable for one or more expirations.")
    oldest_quote_seconds = max(
        int((evaluated_at - item.quote_observed_at).total_seconds()) for item in selected
    )
    if oldest_quote_seconds > 900:
        warnings.append(
            "One or more quotes are older than 15 minutes. Treat this as planning context, "
            "not an executable market."
        )
    cleared = tuple(item for item in selected if item.clears_all_rules)
    expiration_map = build_expiration_map(
        bundle=bundle,
        candidates=selected,
        as_of=evaluated_at.date(),
    )
    if roll_selection is not None:
        direction = "higher" if mode is RadarMode.COVERED_CALL else "same or lower"
        noun = "call" if mode is RadarMode.COVERED_CALL else "put"
        roll_state = (
            RadarState.PARTIAL
            if warnings or any(not item.clears_all_rules for item in selected)
            else RadarState.READY
        )
        return RadarProjection(
            lookup_id=lookup_id,
            state=roll_state,
            symbol=bundle.symbol,
            mode=mode,
            source=bundle.source,
            observed_at=bundle.observed_at,
            underlying_price=spot,
            account=account,
            policy=policy,
            verdict="ROLL REVIEW",
            headline=f"{len(selected)} nearby listed {noun}(s) at later {direction} strikes",
            reasons=(
                "The ladder is the next listed expiries and strikes, not a slogan contest.",
                "Credits use the replacement bid and the current option's buy-to-close ask.",
            ),
            candidates=selected,
            rejected_count=rejected,
            warnings=tuple(warnings),
            expiration_map=expiration_map,
            five_day_move_percent=five_day,
            twenty_day_move_percent=twenty_day,
            range_position_percent=position,
        )
    if not cleared:
        reasons = _wait_reasons(
            mode=mode,
            account=account,
            policy=policy,
            contracts=tuple(bundle.contracts),
            five_day=five_day,
            rejected=rejected,
        )
        return RadarProjection(
            lookup_id=lookup_id,
            state=RadarState.WAIT,
            symbol=bundle.symbol,
            mode=mode,
            source=bundle.source,
            observed_at=bundle.observed_at,
            underlying_price=spot,
            account=account,
            policy=policy,
            verdict="WAIT",
            headline=_planning_headline(
                mode=mode,
                account=account,
                policy=policy,
                five_day=five_day,
            ),
            reasons=reasons,
            candidates=selected,
            rejected_count=rejected,
            warnings=tuple(warnings),
            expiration_map=expiration_map,
            five_day_move_percent=five_day,
            twenty_day_move_percent=twenty_day,
            range_position_percent=position,
        )

    state = RadarState.PARTIAL if warnings or len(cleared) < len(selected) else RadarState.READY
    return RadarProjection(
        lookup_id=lookup_id,
        state=state,
        symbol=bundle.symbol,
        mode=mode,
        source=bundle.source,
        observed_at=bundle.observed_at,
        underlying_price=spot,
        account=account,
        policy=policy,
        verdict="REVIEW",
        headline=f"{len(cleared)} trade-off(s) cleared every saved rule",
        reasons=(
            "Credits use the bid; midpoint is shown only as a market reference.",
            (
                "Research-only rows still need account capacity or a paused rule resolved."
                if len(cleared) < len(selected)
                else "Open the evidence for the measurements and rejected-contract count."
            ),
        ),
        candidates=selected,
        rejected_count=rejected,
        warnings=tuple(warnings),
        expiration_map=expiration_map,
        five_day_move_percent=five_day,
        twenty_day_move_percent=twenty_day,
        range_position_percent=position,
    )


def _include_preferred_candidate(
    selected: tuple[RadarCandidate, ...],
    preferred: RadarCandidate | None,
) -> tuple[RadarCandidate, ...]:
    """Keep one explicitly requested roll target without weakening normal scans."""

    if preferred is None or any(
        candidate.option_symbol == preferred.option_symbol for candidate in selected
    ):
        return selected
    if len(selected) < 9:
        return (*selected, preferred)
    return (*selected[:-1], preferred)


def _candidate(
    contract: RadarMarketContract,
    *,
    spot: Decimal,
    mode: RadarMode,
    account: RadarAccountContext,
    policy: RadarPolicy,
    five_day_move_percent: Decimal | None,
    now: datetime,
    atm_iv: Decimal | None,
) -> RadarCandidate:
    dte = days_to_expiration(contract.expiration_date, as_of=now.date())
    bid = contract.bid or Decimal("0")
    ask = contract.ask or bid
    middle = midpoint(bid, ask)
    width = spread_percent(bid, ask)
    room = contract.strike - spot if mode is RadarMode.COVERED_CALL else spot - contract.strike
    room_percent = room / spot * Decimal("100") if spot else Decimal("0")
    movement = expected_move(spot, atm_iv, dte)
    distance_in_moves = abs(room) / movement if movement and movement > 0 else None
    eligible_contracts = (
        min(account.available_call_lots, policy.allowed_contracts)
        if mode is RadarMode.COVERED_CALL
        else min(
            policy.allowed_contracts,
            int(
                min(account.reserved_cash, policy.reserved_cash)
                // (contract.strike * contract.multiplier)
            ),
        )
    )
    capital_per_share = spot if mode is RadarMode.COVERED_CALL else contract.strike
    effective_entry = contract.strike - bid if mode is RadarMode.CASH_SECURED_PUT else None
    cash_required = (
        contract.strike * contract.multiplier * Decimal(eligible_contracts)
        if mode is RadarMode.CASH_SECURED_PUT
        else None
    )
    premium_per_contract = bid * contract.multiplier
    gates = evaluate_gates(
        contract,
        mode=mode,
        policy=policy,
        account=account,
        spot=spot,
        dte=dte,
        five_day_move_percent=five_day_move_percent,
        now=now,
    )
    failed = tuple(gate.detail for gate in gates if gate.status.value == "fail")
    clears_all_rules = passes(gates)
    reasons = failed or (
        f"{room_percent:.1f}% strike room",
        f"{width:.1f}% bid/ask width",
        f"{dte} days to expiration",
    )
    return RadarCandidate(
        option_symbol=contract.option_symbol,
        label=None,
        strike=contract.strike,
        expiration_date=contract.expiration_date,
        days_to_expiration=dte,
        bid=bid,
        ask=ask,
        midpoint=middle,
        spread_dollars=ask - bid,
        spread_percent=width,
        room_dollars=room,
        room_percent=room_percent,
        expected_move=movement,
        strike_distance_in_moves=distance_in_moves,
        delta=contract.delta,
        implied_volatility=contract.implied_volatility,
        open_interest=contract.open_interest,
        volume=contract.volume,
        quote_observed_at=contract.observed_at,
        premium_per_contract=premium_per_contract,
        bid_credit_per_calendar_day=bid_credit_per_calendar_day(
            premium_per_contract=premium_per_contract,
            dte=dte,
        ),
        premium_dollars=bid * contract.multiplier * Decimal(eligible_contracts),
        simple_annualized_rate_percent=simple_annualized_rate(
            premium_per_share=bid,
            capital_per_share=capital_per_share,
            dte=dte,
        ),
        effective_entry=effective_entry,
        cash_required=cash_required,
        eligible_contracts=eligible_contracts,
        clears_all_rules=clears_all_rules,
        gates=gates,
        reasons=reasons,
        theta=contract.theta,
    )


def _passes_research_gates(candidate: RadarCandidate) -> bool:
    """Keep useful comparisons while preserving account and pause warnings."""

    return all(
        gate.status.value != "fail" or gate.code in _PLANNING_GATE_CODES for gate in candidate.gates
    )


def _passes_roll_research_gates(candidate: RadarCandidate) -> bool:
    """Waive opening-sale filters; the selector still requires a positive bid."""

    return all(
        gate.code != "side" or gate.status.value != "fail" for gate in candidate.gates
    )


def _planning_headline(
    *,
    mode: RadarMode,
    account: RadarAccountContext,
    policy: RadarPolicy,
    five_day: Decimal | None,
) -> str:
    if mode is RadarMode.COVERED_CALL and account.available_call_lots == 0:
        return "Call comparisons loaded; no uncovered share lot is available"
    if (
        mode is RadarMode.COVERED_CALL
        and five_day is not None
        and policy.maximum_five_day_move_percent is not None
        and five_day > policy.maximum_five_day_move_percent
    ):
        return "Call comparisons loaded; your fast-rise pause is active"
    if mode is RadarMode.CASH_SECURED_PUT and (
        policy.maximum_effective_entry is None
        or min(account.reserved_cash, policy.reserved_cash) <= 0
    ):
        return "Put comparisons loaded; finish your buy-price and cash rules"
    return "Comparisons loaded; none is ready under every saved rule"


def _atm_iv_by_expiration(
    contracts: tuple[RadarMarketContract, ...],
    *,
    spot: Decimal,
    mode: RadarMode,
) -> dict[date, Decimal]:
    result: dict[date, Decimal] = {}
    distances: dict[date, Decimal] = {}
    for contract in contracts:
        if contract.option_side is not mode.option_side or contract.implied_volatility is None:
            continue
        distance = abs(contract.strike - spot)
        current = distances.get(contract.expiration_date)
        if current is None or distance < current:
            distances[contract.expiration_date] = distance
            result[contract.expiration_date] = contract.implied_volatility
    return result


def _empty_headline(
    symbol: str | None,
    *,
    mode: RadarMode,
    side_contract_count: int,
    for_roll: bool,
) -> str:
    if not side_contract_count:
        return f"No supported {mode.option_side.value} contracts returned for {symbol}"
    if for_roll:
        return f"{symbol} chain loaded; no nearby listed replacement"
    return f"{symbol} chain loaded; no contract clears the current filters"


def _wait_reasons(
    *,
    mode: RadarMode,
    account: RadarAccountContext,
    policy: RadarPolicy,
    contracts: tuple[RadarMarketContract, ...],
    five_day: Decimal | None,
    rejected: int,
    for_roll: bool = False,
) -> tuple[str, ...]:
    if for_roll:
        if not contracts:
            return ("The source returned no supported contracts in this window.",)
        return (
            "Later listed contracts need a positive bid and a protective strike.",
        )
    reasons: list[str] = []
    if mode is RadarMode.COVERED_CALL and account.available_call_lots == 0:
        reasons.append("No uncommitted 100-share lot is available for another covered call.")
    if mode is RadarMode.CASH_SECURED_PUT:
        if policy.maximum_effective_entry is None:
            reasons.append("Set the highest effective stock purchase price you would accept.")
        if min(account.reserved_cash, policy.reserved_cash) <= 0:
            reasons.append("Reserve cash explicitly before comparing cash-secured puts.")
    if (
        mode is RadarMode.COVERED_CALL
        and five_day is not None
        and policy.maximum_five_day_move_percent is not None
        and five_day > policy.maximum_five_day_move_percent
    ):
        reasons.append(
            f"The stock rose {five_day:.1f}% in five sessions, above the saved acceleration pause."
        )
    if not contracts:
        reasons.append("The source returned no supported contracts in this DTE window.")
    if rejected:
        reasons.append(
            f"The chain returned contracts, but {rejected} missed the "
            f"{policy.minimum_annualized_rate_percent:.1f}% minimum premium rate or another "
            "hard quote, liquidity, distance, or policy filter."
        )
    return tuple(reasons[:3]) or ("No contract produced a complete, auditable comparison.",)


def _empty_projection(
    *,
    lookup_id: str | None,
    bundle: RadarMarketBundle,
    mode: RadarMode,
    account: RadarAccountContext,
    policy: RadarPolicy,
    state: RadarState,
    headline: str,
    reasons: tuple[str, ...],
    warnings: tuple[str, ...],
    rejected_count: int = 0,
    five_day: Decimal | None = None,
    twenty_day: Decimal | None = None,
    range_position_percent: Decimal | None = None,
) -> RadarProjection:
    return RadarProjection(
        lookup_id=lookup_id,
        state=state,
        symbol=bundle.symbol,
        mode=mode,
        source=bundle.source,
        observed_at=bundle.observed_at,
        underlying_price=bundle.underlying_price,
        account=account,
        policy=policy,
        verdict="WAIT" if state is RadarState.WAIT else "DATA CHECK",
        headline=headline,
        reasons=reasons,
        candidates=(),
        rejected_count=rejected_count,
        warnings=warnings,
        expiration_map=None,
        five_day_move_percent=five_day,
        twenty_day_move_percent=twenty_day,
        range_position_percent=range_position_percent,
    )
