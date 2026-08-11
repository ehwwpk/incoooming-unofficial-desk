from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from schwab_dashboard.application.dashboard.models import (
    LiveOpenCallPosition,
    LivePositionBook,
    LiveUnderlyingPosition,
    PositionSummary,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def build_live_position_book(
    positions: Sequence[PositionSummary], *, as_of: date
) -> LivePositionBook:
    holdings = {
        position.symbol: position
        for position in positions
        if position.asset_type.upper() != "OPTION" and position.quantity > ZERO
    }
    calls_by_symbol: defaultdict[str, list[LiveOpenCallPosition]] = defaultdict(list)
    for position in positions:
        if not _is_short_call(position):
            continue
        assert position.underlying_symbol is not None
        assert position.expiration_date is not None
        assert position.strike is not None
        contracts = int(abs(position.quantity))
        holding = holdings.get(position.underlying_symbol)
        underlying_price = holding.mark if holding else None
        distance = position.strike - underlying_price if underlying_price is not None else None
        distance_percent = (
            distance / underlying_price * HUNDRED
            if distance is not None and underlying_price
            else None
        )
        calls_by_symbol[position.underlying_symbol].append(
            LiveOpenCallPosition(
                account_mask=position.account_mask,
                option_symbol=position.symbol,
                underlying_symbol=position.underlying_symbol,
                contracts=contracts,
                expires_on=position.expiration_date,
                days_to_expiration=max(0, (position.expiration_date - as_of).days),
                strike=position.strike,
                entry_credit_per_share=position.average_price,
                estimated_mark_per_share=position.mark,
                market_value=position.market_value,
                open_profit_loss=position.open_profit_loss,
                day_profit_loss=position.day_profit_loss,
                underlying_price=underlying_price,
                strike_distance_per_share=distance,
                strike_distance_percent=distance_percent,
            )
        )

    underlyings: list[LiveUnderlyingPosition] = []
    all_calls: list[LiveOpenCallPosition] = []
    for symbol, calls in sorted(calls_by_symbol.items()):
        ordered_calls = tuple(sorted(calls, key=lambda item: (item.expires_on, item.strike)))
        all_calls.extend(ordered_calls)
        holding = holdings.get(symbol)
        shares = int(holding.quantity) if holding is not None else 0
        capacity = max(0, shares // 100)
        open_contracts = sum(call.contracts for call in ordered_calls)
        covered_contracts = min(capacity, open_contracts)
        underlyings.append(
            LiveUnderlyingPosition(
                symbol=symbol,
                description=holding.description
                if holding is not None
                else "No matching long shares",
                shares=shares,
                average_price=holding.average_price if holding is not None else None,
                current_price=holding.mark if holding is not None else None,
                market_value=holding.market_value if holding is not None else None,
                day_profit_loss=holding.day_profit_loss if holding is not None else None,
                contract_capacity=capacity,
                open_call_contracts=open_contracts,
                covered_contracts=covered_contracts,
                uncovered_contracts=max(0, open_contracts - capacity),
                coverage_percent=(
                    Decimal(covered_contracts) / Decimal(capacity) * HUNDRED if capacity else ZERO
                ),
                open_mark_profit_loss=sum(
                    (call.open_profit_loss or ZERO for call in ordered_calls), ZERO
                ),
                calls=ordered_calls,
            )
        )

    capacity = sum(item.contract_capacity for item in underlyings)
    open_contracts = sum(item.open_call_contracts for item in underlyings)
    covered_contracts = sum(item.covered_contracts for item in underlyings)
    return LivePositionBook(
        underlyings=tuple(underlyings),
        calls=tuple(all_calls),
        total_shares=sum(item.shares for item in underlyings),
        contract_capacity=capacity,
        open_call_positions=len(all_calls),
        open_call_contracts=open_contracts,
        covered_contracts=covered_contracts,
        uncovered_contracts=sum(item.uncovered_contracts for item in underlyings),
        coverage_percent=(
            Decimal(covered_contracts) / Decimal(capacity) * HUNDRED if capacity else ZERO
        ),
        open_mark_profit_loss=sum((call.open_profit_loss or ZERO for call in all_calls), ZERO),
    )


def _is_short_call(position: PositionSummary) -> bool:
    return (
        position.asset_type.upper() == "OPTION"
        and position.quantity < ZERO
        and position.option_type == "CALL"
        and position.underlying_symbol is not None
        and position.expiration_date is not None
        and position.strike is not None
    )
