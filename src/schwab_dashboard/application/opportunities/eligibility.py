from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from schwab_dashboard.application.opportunities.quote_math import (
    simple_annualized_rate,
    spread_percent,
)
from schwab_dashboard.domain.market import QuoteQuality
from schwab_dashboard.domain.opportunity import (
    RadarAccountContext,
    RadarGate,
    RadarGateStatus,
    RadarMarketContract,
    RadarMode,
    RadarPolicy,
)


def evaluate_gates(
    contract: RadarMarketContract,
    *,
    mode: RadarMode,
    policy: RadarPolicy,
    account: RadarAccountContext,
    spot: Decimal,
    dte: int,
    five_day_move_percent: Decimal | None,
    now: datetime,
) -> tuple[RadarGate, ...]:
    gates = [
        _gate(
            "side",
            "Option type",
            contract.option_side is mode.option_side,
            f"{contract.option_side.value.upper()} contract",
        ),
        _gate(
            "dte",
            "Time window",
            policy.minimum_dte <= dte <= policy.maximum_dte,
            f"{dte} DTE; policy allows {policy.minimum_dte}-{policy.maximum_dte}",
        ),
        _quote_gate(contract),
        _annualized_rate_gate(
            contract,
            mode=mode,
            policy=policy,
            spot=spot,
            dte=dte,
        ),
        _quote_age_gate(contract, policy=policy, now=now),
        _spread_gate(contract, policy=policy),
        _open_interest_gate(contract, policy=policy),
        _volume_gate(contract, policy=policy),
        _momentum_gate(
            mode=mode,
            policy=policy,
            five_day_move_percent=five_day_move_percent,
        ),
    ]
    if mode is RadarMode.COVERED_CALL:
        gates.extend(_call_gates(contract, policy=policy, account=account, spot=spot))
    else:
        gates.extend(_put_gates(contract, policy=policy, account=account, spot=spot))
    return tuple(gates)


def passes(gates: tuple[RadarGate, ...]) -> bool:
    return all(gate.status is not RadarGateStatus.FAIL for gate in gates)


def _call_gates(
    contract: RadarMarketContract,
    *,
    policy: RadarPolicy,
    account: RadarAccountContext,
    spot: Decimal,
) -> tuple[RadarGate, ...]:
    room_percent = (contract.strike - spot) / spot * Decimal("100") if spot else Decimal("0")
    return (
        _gate(
            "covered_lots",
            "Available shares",
            min(account.available_call_lots, policy.allowed_contracts) > 0,
            (
                f"{account.available_call_lots} available covered lot(s); "
                f"policy allows {policy.allowed_contracts}"
            ),
        ),
        _gate(
            "otm_call",
            "Strike above spot",
            contract.strike >= spot,
            f"${contract.strike} strike versus ${spot} spot",
        ),
        _gate(
            "strike_distance",
            "Minimum strike room",
            room_percent >= policy.minimum_strike_distance_percent,
            (
                f"{room_percent:.1f}% room; policy requires "
                f"{policy.minimum_strike_distance_percent:.1f}%"
            ),
        ),
        _optional_floor_gate(contract, policy=policy),
    )


def _put_gates(
    contract: RadarMarketContract,
    *,
    policy: RadarPolicy,
    account: RadarAccountContext,
    spot: Decimal,
) -> tuple[RadarGate, ...]:
    cash_per_contract = contract.strike * contract.multiplier
    effective_entry = contract.strike - (contract.bid or Decimal("0"))
    cash_available = min(account.reserved_cash, policy.reserved_cash)
    room_percent = (spot - contract.strike) / spot * Decimal("100") if spot else Decimal("0")
    return (
        _gate(
            "reserved_cash",
            "Reserved cash",
            cash_per_contract > 0 and cash_available >= cash_per_contract,
            f"${cash_available:,.0f} reserved; ${cash_per_contract:,.0f} required per contract",
        ),
        _gate(
            "otm_put",
            "Strike at or below spot",
            contract.strike <= spot,
            f"${contract.strike} strike versus ${spot} spot",
        ),
        _gate(
            "strike_distance",
            "Minimum discount",
            room_percent >= policy.minimum_strike_distance_percent,
            (
                f"{room_percent:.1f}% below spot; policy requires "
                f"{policy.minimum_strike_distance_percent:.1f}%"
            ),
        ),
        _optional_entry_gate(effective_entry, policy=policy),
    )


def _quote_gate(contract: RadarMarketContract) -> RadarGate:
    valid = (
        contract.quote_quality is QuoteQuality.COMPLETE
        and contract.bid is not None
        and contract.ask is not None
        and contract.bid > 0
        and contract.ask >= contract.bid
    )
    return _gate(
        "two_sided_quote",
        "Tradable quote",
        valid,
        (
            f"bid ${contract.bid} / ask ${contract.ask}"
            if contract.bid is not None and contract.ask is not None
            else "A complete bid and ask are required"
        ),
    )


def _annualized_rate_gate(
    contract: RadarMarketContract,
    *,
    mode: RadarMode,
    policy: RadarPolicy,
    spot: Decimal,
    dte: int,
) -> RadarGate:
    capital_per_share = spot if mode is RadarMode.COVERED_CALL else contract.strike
    rate = simple_annualized_rate(
        premium_per_share=contract.bid or Decimal("0"),
        capital_per_share=capital_per_share,
        dte=dte,
    )
    return _gate(
        "annualized_rate",
        "Minimum premium rate",
        rate >= policy.minimum_annualized_rate_percent,
        (
            f"{rate:.1f}% simple annualized premium rate; policy requires "
            f"{policy.minimum_annualized_rate_percent:.1f}%"
        ),
    )


def _quote_age_gate(
    contract: RadarMarketContract,
    *,
    policy: RadarPolicy,
    now: datetime,
) -> RadarGate:
    age = max(0, int((now - contract.observed_at).total_seconds()))
    return _gate(
        "quote_age",
        "Quote freshness",
        age <= policy.maximum_quote_age_seconds,
        f"{age}s old; limit {policy.maximum_quote_age_seconds}s",
    )


def _spread_gate(contract: RadarMarketContract, *, policy: RadarPolicy) -> RadarGate:
    if contract.bid is None or contract.ask is None or contract.ask < contract.bid:
        return RadarGate(
            code="spread",
            label="Bid/ask width",
            status=RadarGateStatus.FAIL,
            detail="Spread is unavailable without a valid two-sided quote",
        )
    width = spread_percent(contract.bid, contract.ask)
    return _gate(
        "spread",
        "Bid/ask width",
        width <= policy.maximum_spread_percent,
        f"{width:.1f}% wide; policy limit {policy.maximum_spread_percent:.1f}%",
    )


def _open_interest_gate(contract: RadarMarketContract, *, policy: RadarPolicy) -> RadarGate:
    if contract.open_interest is None:
        return RadarGate(
            code="open_interest",
            label="Open interest",
            status=(
                RadarGateStatus.UNKNOWN
                if policy.minimum_open_interest == 0
                else RadarGateStatus.FAIL
            ),
            detail="Source did not provide open interest",
        )
    return _gate(
        "open_interest",
        "Open interest",
        contract.open_interest >= policy.minimum_open_interest,
        f"{contract.open_interest:,}; policy minimum {policy.minimum_open_interest:,}",
    )


def _volume_gate(contract: RadarMarketContract, *, policy: RadarPolicy) -> RadarGate:
    if contract.volume is None:
        return RadarGate(
            code="volume",
            label="Session volume",
            status=RadarGateStatus.UNKNOWN if policy.minimum_volume == 0 else RadarGateStatus.FAIL,
            detail="Source did not provide session volume",
        )
    return _gate(
        "volume",
        "Session volume",
        contract.volume >= policy.minimum_volume,
        f"{contract.volume:,}; policy minimum {policy.minimum_volume:,}",
    )


def _momentum_gate(
    *,
    mode: RadarMode,
    policy: RadarPolicy,
    five_day_move_percent: Decimal | None,
) -> RadarGate:
    if mode is RadarMode.CASH_SECURED_PUT or policy.maximum_five_day_move_percent is None:
        return RadarGate(
            code="fast_move",
            label="Recent movement",
            status=RadarGateStatus.PASS,
            detail="No covered-call acceleration pause is configured",
        )
    if five_day_move_percent is None:
        return RadarGate(
            code="fast_move",
            label="Recent movement",
            status=RadarGateStatus.UNKNOWN,
            detail="Five-session history is unavailable",
        )
    return _gate(
        "fast_move",
        "Recent movement",
        five_day_move_percent <= policy.maximum_five_day_move_percent,
        (
            f"{five_day_move_percent:+.1f}% in five sessions; pause above "
            f"+{policy.maximum_five_day_move_percent:.1f}%"
        ),
    )


def _optional_floor_gate(contract: RadarMarketContract, *, policy: RadarPolicy) -> RadarGate:
    if policy.minimum_strike is None:
        return RadarGate(
            code="minimum_strike",
            label="Minimum strike",
            status=RadarGateStatus.UNKNOWN,
            detail="No symbol-specific minimum strike is saved",
        )
    return _gate(
        "minimum_strike",
        "Minimum strike",
        contract.strike >= policy.minimum_strike,
        f"${contract.strike} strike; saved floor ${policy.minimum_strike}",
    )


def _optional_entry_gate(effective_entry: Decimal, *, policy: RadarPolicy) -> RadarGate:
    if policy.maximum_effective_entry is None:
        return RadarGate(
            code="effective_entry",
            label="Acceptable buy price",
            status=RadarGateStatus.UNKNOWN,
            detail=(
                f"${effective_entry:.2f} effective entry; save the highest purchase "
                "price you would accept"
            ),
        )
    return _gate(
        "effective_entry",
        "Acceptable buy price",
        effective_entry <= policy.maximum_effective_entry,
        f"${effective_entry:.2f} effective entry; limit ${policy.maximum_effective_entry:.2f}",
    )


def _gate(code: str, label: str, passed: bool, detail: str) -> RadarGate:
    return RadarGate(
        code=code,
        label=label,
        status=RadarGateStatus.PASS if passed else RadarGateStatus.FAIL,
        detail=detail,
    )
