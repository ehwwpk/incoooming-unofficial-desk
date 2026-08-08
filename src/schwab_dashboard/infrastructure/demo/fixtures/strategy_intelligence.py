from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import (
    StrategyInsight,
    UnderlyingCallStats,
)

D = Decimal


def _money(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.0f}"


def build_strategy_insights(
    underlyings: Sequence[UnderlyingCallStats],
) -> tuple[StrategyInsight, ...]:
    """Build deterministic internal book telemetry without external headlines."""
    by_symbol = {item.symbol: item for item in underlyings}
    insights: list[StrategyInsight] = []

    ktos = by_symbol.get("KTOS")
    if ktos is not None:
        stressed_call = max(
            ktos.open_call_clocks,
            key=lambda call: call.option_value_vs_credit_percent,
            default=None,
        )
        if stressed_call is not None and stressed_call.option_value_vs_credit_percent > D("100"):
            insights.append(
                StrategyInsight(
                    sequence=len(insights) + 1,
                    symbol=ktos.symbol,
                    category="MARK ANOMALY",
                    headline="Current option value is above premium received",
                    detail=(
                        f"Sep {stressed_call.expires_on.day} ${stressed_call.strike:g}C is "
                        f"{stressed_call.option_value_vs_credit_percent}% of original credit; "
                        f"open P/L is {_money(stressed_call.open_profit_loss)}."
                    ),
                    metric=f"{stressed_call.option_value_vs_credit_percent}%",
                    severity="critical",
                )
            )

    cvx = by_symbol.get("CVX")
    if cvx is not None and cvx.dividend_overlap_contracts and cvx.next_ex_dividend_date is not None:
        insights.append(
            StrategyInsight(
                sequence=len(insights) + 1,
                symbol=cvx.symbol,
                category="CALENDAR OVERLAP",
                headline="Open calls cross the next simulated ex-dividend date",
                detail=(
                    f"{cvx.dividend_overlap_contracts} contracts extend beyond "
                    f"{cvx.next_ex_dividend_date:%b %d}; confirm moneyness and time value."
                ),
                metric=f"{cvx.dividend_overlap_contracts} CALLS",
                severity="warning",
            )
        )

    if underlyings:
        highest_iv = max(underlyings, key=lambda item: item.average_open_call_iv_percent)
        lowest_iv = min(underlyings, key=lambda item: item.average_open_call_iv_percent)
        iv_spread = highest_iv.average_open_call_iv_percent - lowest_iv.average_open_call_iv_percent
        insights.append(
            StrategyInsight(
                sequence=len(insights) + 1,
                symbol=highest_iv.symbol,
                category="IV DISPERSION",
                headline="Open-call IV is the highest in the tracked book",
                detail=(
                    f"{highest_iv.average_open_call_iv_percent}% average IV is "
                    f"{iv_spread}% points above {lowest_iv.symbol}; compare premium with gap risk."
                ),
                metric=f"+{iv_spread} PT",
                severity="watch",
            )
        )

    available = max(
        (item for item in underlyings if item.contract_capacity > item.active_contracts),
        key=lambda item: (item.contract_capacity - item.active_contracts, item.symbol),
        default=None,
    )
    if available is not None:
        open_lots = available.contract_capacity - available.active_contracts
        insights.append(
            StrategyInsight(
                sequence=len(insights) + 1,
                symbol=available.symbol,
                category="COVERAGE CAPACITY",
                headline="Share-backed call capacity remains unused",
                detail=(
                    f"{open_lots} contract lot is uncovered by an open call; "
                    "capacity is context, not a recommendation to sell."
                ),
                metric=f"{open_lots} LOT",
                severity="info",
            )
        )

    return tuple(insights)
