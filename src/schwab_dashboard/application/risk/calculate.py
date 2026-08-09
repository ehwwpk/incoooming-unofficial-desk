from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from schwab_dashboard.application.risk.models import (
    OpenCallRiskInput,
    OpenCallRiskView,
    OpenRiskSummary,
)
from schwab_dashboard.domain.analytics import (
    CalculationContext,
    DataQuality,
    ValueStatus,
)
from schwab_dashboard.domain.market import QuoteQuality

ONE_HUNDRED = Decimal("100")


def calculate_open_risk(items: tuple[OpenCallRiskInput, ...]) -> OpenRiskSummary:
    if not items:
        raise ValueError("at least one open call is required")
    as_of_values = {item.observed_at for item in items}
    if len(as_of_values) != 1:
        raise ValueError("open-risk inputs must share one observed_at timestamp")

    positions = tuple(_calculate_position(item) for item in items)
    total_weight = sum(
        (item.contracts_short * item.premium_multiplier for item in items), Decimal(0)
    )
    delta_weight = sum(
        (
            item.contracts_short * item.premium_multiplier
            for item in items
            if item.delta is not None
        ),
        Decimal(0),
    )
    theta_weight = sum(
        (
            item.contracts_short * item.premium_multiplier
            for item in items
            if item.theta is not None
        ),
        Decimal(0),
    )
    complete = (
        delta_weight == total_weight
        and theta_weight == total_weight
        and all(_has_complete_market_context(item) for item in items)
    )
    return OpenRiskSummary(
        positions=positions,
        called_away_notional=sum((row.called_away_notional for row in positions), Decimal(0)),
        obligated_shares=sum((row.obligated_shares for row in positions), Decimal(0)),
        current_liability=_sum_optional(row.current_liability for row in positions),
        theta_estimate_per_day=_sum_optional(row.theta_estimate_per_day for row in positions),
        dollar_delta_for_one_percent_move=_sum_optional(
            row.dollar_delta_for_one_percent_move for row in positions
        ),
        delta_coverage_percent=_percent(delta_weight, total_weight),
        theta_coverage_percent=_percent(theta_weight, total_weight),
        context=CalculationContext(
            as_of=items[0].observed_at,
            status=ValueStatus.ESTIMATED,
            method="signed-open-call-greek-aggregation",
            method_version="1.0.0",
            source_ids=tuple(item.contract_key for item in items),
            quality=DataQuality.COMPLETE if complete else DataQuality.PARTIAL,
        ),
    )


def _calculate_position(item: OpenCallRiskInput) -> OpenCallRiskView:
    obligated_shares = item.contracts_short * item.deliverable_share_quantity
    called_away_notional = obligated_shares * item.strike
    distance = item.strike - item.underlying_price
    distance_percent = None
    if item.underlying_price != 0:
        distance_percent = distance / item.underlying_price * ONE_HUNDRED
    current_liability = _scaled(item.option_mark, item.contracts_short, item.premium_multiplier)
    entry_value = _scaled(item.entry_credit, item.contracts_short, item.premium_multiplier)
    open_mark_profit_loss = None
    if entry_value is not None and current_liability is not None:
        open_mark_profit_loss = entry_value - current_liability
    spread_percent = None
    mark = item.option_mark
    if item.bid is not None and item.ask is not None and mark is not None and mark != 0:
        spread_percent = (item.ask - item.bid) / mark * ONE_HUNDRED
    scale = item.contracts_short * item.premium_multiplier
    delta_share_equivalent = -scale * item.delta if item.delta is not None else None
    dollar_delta = None
    if delta_share_equivalent is not None:
        dollar_delta = delta_share_equivalent * item.underlying_price / ONE_HUNDRED
    return OpenCallRiskView(
        contract_key=item.contract_key,
        symbol=item.symbol,
        obligated_shares=obligated_shares,
        called_away_notional=called_away_notional,
        distance_to_strike=distance,
        distance_to_strike_percent=distance_percent,
        current_liability=current_liability,
        open_mark_profit_loss=open_mark_profit_loss,
        spread_percent_of_mark=spread_percent,
        delta_share_equivalent=delta_share_equivalent,
        dollar_delta_for_one_percent_move=dollar_delta,
        gamma_per_dollar_squared=-scale * item.gamma if item.gamma is not None else None,
        theta_estimate_per_day=-scale * item.theta if item.theta is not None else None,
        vega_per_volatility_point=-scale * item.vega if item.vega is not None else None,
        quote_quality=item.quote_quality,
    )


def _scaled(value: Decimal | None, quantity: Decimal, multiplier: Decimal) -> Decimal | None:
    return value * quantity * multiplier if value is not None else None


def _has_complete_market_context(item: OpenCallRiskInput) -> bool:
    return item.quote_quality is QuoteQuality.COMPLETE and all(
        value is not None
        for value in (
            item.bid,
            item.ask,
            item.option_mark,
            item.delta,
            item.gamma,
            item.theta,
            item.vega,
        )
    )


def _sum_optional(values: Iterable[Decimal | None]) -> Decimal | None:
    present = [value for value in values if value is not None]
    return sum(present, Decimal(0)) if present else None


def _percent(numerator: Decimal, denominator: Decimal) -> Decimal:
    return numerator / denominator * ONE_HUNDRED if denominator else Decimal(0)
