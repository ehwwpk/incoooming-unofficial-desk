from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from schwab_dashboard.application.risk.models import (
    OpenOptionRiskInput,
    OpenOptionRiskView,
    OpenRiskSummary,
    UnderlyingEquityRiskInput,
    UnderlyingRiskView,
)
from schwab_dashboard.domain.analytics import (
    CalculationContext,
    DataQuality,
    ValueStatus,
)
from schwab_dashboard.domain.market import QuoteQuality

ONE_HUNDRED = Decimal("100")


def calculate_open_risk(
    items: tuple[OpenOptionRiskInput, ...],
    *,
    equities: tuple[UnderlyingEquityRiskInput, ...] = (),
) -> OpenRiskSummary:
    if not items:
        raise ValueError("at least one open option is required")

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
    gamma_weight = _covered_weight(items, "gamma")
    vega_weight = _covered_weight(items, "vega")
    quote_weight = sum(
        (
            item.contracts_short * item.premium_multiplier
            for item in items
            if item.quote_quality is QuoteQuality.COMPLETE
        ),
        Decimal(0),
    )
    complete = (
        delta_weight == total_weight
        and theta_weight == total_weight
        and gamma_weight == total_weight
        and vega_weight == total_weight
        and all(_has_complete_market_context(item) for item in items)
    )
    underlyings = _calculate_underlyings(items, positions, equities)
    option_delta = _sum_optional(row.delta_share_equivalent for row in positions)
    equity_delta = sum((item.shares for item in equities), Decimal(0))
    option_one_percent = _sum_optional(
        row.dollar_delta_for_one_percent_move for row in positions
    )
    equity_one_percent = sum(
        (item.shares * item.underlying_price / ONE_HUNDRED for item in equities),
        Decimal(0),
    )
    observed = tuple(item.observed_at for item in items)
    estimated_one_percent = (
        equity_one_percent + option_one_percent
        if option_one_percent is not None
        else None
    )
    return OpenRiskSummary(
        positions=positions,
        underlyings=underlyings,
        called_away_notional=sum((row.called_away_notional for row in positions), Decimal(0)),
        obligated_shares=sum((row.obligated_shares for row in positions), Decimal(0)),
        current_liability=_sum_optional(row.current_liability for row in positions),
        theta_estimate_per_day=_sum_optional(row.theta_estimate_per_day for row in positions),
        dollar_delta_for_one_percent_move=option_one_percent,
        estimated_value_change_for_one_percent_move=estimated_one_percent,
        option_delta_share_equivalent=option_delta,
        net_delta_share_equivalent=(
            equity_delta + option_delta if option_delta is not None else None
        ),
        gamma_delta_change_for_one_dollar_move=_sum_optional(
            row.gamma_per_dollar_squared for row in positions
        ),
        vega_per_volatility_point=_sum_optional(
            row.vega_per_volatility_point for row in positions
        ),
        delta_coverage_percent=_percent(delta_weight, total_weight),
        theta_coverage_percent=_percent(theta_weight, total_weight),
        gamma_coverage_percent=_percent(gamma_weight, total_weight),
        vega_coverage_percent=_percent(vega_weight, total_weight),
        quote_coverage_percent=_percent(quote_weight, total_weight),
        oldest_quote_at=min(observed),
        newest_quote_at=max(observed),
        context=CalculationContext(
            as_of=min(observed),
            status=ValueStatus.ESTIMATED,
            method="signed-open-option-greek-aggregation",
            method_version="2.0.0",
            source_ids=tuple(item.contract_key for item in items),
            quality=DataQuality.COMPLETE if complete else DataQuality.PARTIAL,
        ),
    )


def _calculate_position(item: OpenOptionRiskInput) -> OpenOptionRiskView:
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
    return OpenOptionRiskView(
        contract_key=item.contract_key,
        symbol=item.symbol,
        option_type=item.option_type.upper(),
        contracts_short=item.contracts_short,
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


def _has_complete_market_context(item: OpenOptionRiskInput) -> bool:
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


def _covered_weight(items: tuple[OpenOptionRiskInput, ...], field: str) -> Decimal:
    return sum(
        (
            item.contracts_short * item.premium_multiplier
            for item in items
            if getattr(item, field) is not None
        ),
        Decimal(0),
    )


def _calculate_underlyings(
    items: tuple[OpenOptionRiskInput, ...],
    positions: tuple[OpenOptionRiskView, ...],
    equities: tuple[UnderlyingEquityRiskInput, ...],
) -> tuple[UnderlyingRiskView, ...]:
    equity_by_symbol = {item.symbol: item for item in equities}
    symbols = sorted({item.symbol for item in items} | set(equity_by_symbol))
    rows: list[UnderlyingRiskView] = []
    for symbol in symbols:
        source_rows = tuple(item for item in items if item.symbol == symbol)
        position_rows = tuple(item for item in positions if item.symbol == symbol)
        equity = equity_by_symbol.get(symbol)
        shares = equity.shares if equity is not None else Decimal(0)
        price = (
            equity.underlying_price
            if equity is not None
            else source_rows[0].underlying_price
        )
        total_weight = sum(
            (item.contracts_short * item.premium_multiplier for item in source_rows),
            Decimal(0),
        )
        option_delta = _sum_optional(
            item.delta_share_equivalent for item in position_rows
        )
        option_one_percent = _sum_optional(
            item.dollar_delta_for_one_percent_move for item in position_rows
        )
        equity_one_percent = shares * price / ONE_HUNDRED
        estimated_one_percent = (
            equity_one_percent + option_one_percent
            if option_one_percent is not None
            else None
        )
        rows.append(
            UnderlyingRiskView(
                symbol=symbol,
                shares=shares,
                option_contracts=sum(
                    (item.contracts_short for item in source_rows), Decimal(0)
                ),
                option_delta_share_equivalent=option_delta,
                net_delta_share_equivalent=(
                    shares + option_delta if option_delta is not None else None
                ),
                estimated_value_change_for_one_percent_move=estimated_one_percent,
                theta_estimate_per_day=_sum_optional(
                    item.theta_estimate_per_day for item in position_rows
                ),
                gamma_delta_change_for_one_dollar_move=_sum_optional(
                    item.gamma_per_dollar_squared for item in position_rows
                ),
                vega_per_volatility_point=_sum_optional(
                    item.vega_per_volatility_point for item in position_rows
                ),
                delta_coverage_percent=_percent(
                    _covered_weight(source_rows, "delta"), total_weight
                ),
                theta_coverage_percent=_percent(
                    _covered_weight(source_rows, "theta"), total_weight
                ),
                gamma_coverage_percent=_percent(
                    _covered_weight(source_rows, "gamma"), total_weight
                ),
                vega_coverage_percent=_percent(
                    _covered_weight(source_rows, "vega"), total_weight
                ),
            )
        )
    return tuple(rows)
