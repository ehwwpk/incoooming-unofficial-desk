from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import (
    CallSaleRecord,
    CoveredCallPortfolioSummary,
    OpenCallClock,
    UnderlyingCallStats,
)
from schwab_dashboard.application.values import sum_if_complete
from schwab_dashboard.infrastructure.demo.fixtures.daily_prices import DAILY_CLOSES
from schwab_dashboard.infrastructure.demo.fixtures.holdings import HOLDINGS, HoldingFixture
from schwab_dashboard.infrastructure.demo.fixtures.name_windows import build_name_windows
from schwab_dashboard.infrastructure.demo.fixtures.open_call_metrics import OPEN_CALL_METRICS
from schwab_dashboard.infrastructure.demo.fixtures.price_paths import (
    build_daily_price_points,
    build_price_events,
    build_share_trade_events,
)
from schwab_dashboard.infrastructure.demo.fixtures.roll_quotes import ROLL_QUOTE_CANDIDATES
from schwab_dashboard.infrastructure.demo.fixtures.share_trades import SHARE_TRADES

D = Decimal
ZERO = D("0")
TENTH = D("0.1")
HUNDRED = D("100")
YEAR_DAYS = D("365")
QUARTER_DAYS = D("85")


def build_underlying_stats(
    records: Sequence[CallSaleRecord],
    as_of: date,
) -> tuple[UnderlyingCallStats, ...]:
    return tuple(_summarize_holding(holding, records, as_of) for holding in HOLDINGS)


def build_covered_call_summary(
    records: Sequence[CallSaleRecord],
    underlyings: Sequence[UnderlyingCallStats],
) -> CoveredCallPortfolioSummary:
    completed = [record for record in records if record.outcome != "Open"]
    wins = sum(1 for record in completed if record.net_cash > ZERO)
    stock_value = sum((underlying.market_value for underlying in underlyings), ZERO)
    net_option_cash = sum((record.net_cash for record in records), ZERO)
    gross_premium = sum((record.gross_premium for record in records), ZERO)
    dividends = sum((underlying.quarter_dividends for underlying in underlyings), ZERO)
    open_call_credit = sum(
        (record.gross_premium for record in records if record.outcome == "Open"), ZERO
    )
    open_call_mark_value = sum_if_complete(
        (
            clock.current_option_value
            for underlying in underlyings
            for clock in underlying.open_call_clocks
        ),
    )
    assert open_call_mark_value is not None
    annual_factor = YEAR_DAYS / QUARTER_DAYS
    return CoveredCallPortfolioSummary(
        total_shares=sum((item.shares for item in underlyings), ZERO),
        contract_capacity=sum(item.contract_capacity for item in underlyings),
        active_contracts=sum(item.active_contracts for item in underlyings),
        coverage_percent=_ratio(
            sum(item.active_contracts for item in underlyings),
            sum(item.contract_capacity for item in underlyings),
        ),
        call_tickets=len(records),
        contracts_sold=sum(record.contracts for record in records),
        expired_contracts=_contracts(records, "Expired"),
        closed_contracts=_contracts(records, "Closed"),
        rolled_contracts=_contracts(records, "Rolled"),
        assigned_contracts=_contracts(records, "Assigned"),
        called_away_shares=D(_contracts(records, "Assigned") * 100),
        gross_premium=gross_premium,
        buyback_cost=sum((record.buyback_cost for record in records), ZERO),
        net_option_cash=net_option_cash,
        realized_option_income=sum((record.net_cash for record in completed), ZERO),
        open_call_credit=open_call_credit,
        open_call_mark_value=open_call_mark_value,
        open_mark_profit_loss=open_call_credit - open_call_mark_value,
        dividends=dividends,
        total_cash_income=net_option_cash + dividends,
        win_rate=_ratio(wins, len(completed)),
        annualized_option_yield=(net_option_cash / stock_value * annual_factor * 100).quantize(
            TENTH
        ),
        annualized_total_cash_yield=(
            (net_option_cash + dividends) / stock_value * annual_factor * 100
        ).quantize(TENTH),
        premium_capture_percent=(net_option_cash / gross_premium * 100).quantize(TENTH),
    )


def _summarize_holding(
    holding: HoldingFixture,
    records: Sequence[CallSaleRecord],
    as_of: date,
) -> UnderlyingCallStats:
    symbol_records = [record for record in records if record.symbol == holding.symbol]
    completed = [record for record in symbol_records if record.outcome != "Open"]
    open_records = [record for record in symbol_records if record.outcome == "Open"]
    contract_count = sum(record.contracts for record in symbol_records)
    active_contracts = sum(record.contracts for record in open_records)
    market_value = holding.current_price * holding.shares
    net_option_cash = sum((record.net_cash for record in symbol_records), ZERO)
    gross_premium = sum((record.gross_premium for record in symbol_records), ZERO)
    weighted_upside = sum(
        (
            _required_decimal(record.strike_upside_percent) * record.contracts
            for record in symbol_records
        ),
        ZERO,
    )
    weighted_dte = sum(record.days_to_expiration * record.contracts for record in symbol_records)
    original_cost_basis = holding.average_cost * holding.shares
    lifetime_income = holding.lifetime_option_income + holding.lifetime_dividends
    income_adjusted_basis = original_cost_basis - lifetime_income
    annual_factor = YEAR_DAYS / QUARTER_DAYS
    price_points = build_daily_price_points(DAILY_CLOSES[holding.symbol])
    prices = [point.price for point in price_points]
    open_call_clocks = tuple(
        _open_call_clock(record, holding.current_price, as_of) for record in open_records
    )
    return UnderlyingCallStats(
        symbol=holding.symbol,
        company_name=holding.company_name,
        shares=D(holding.shares),
        average_cost=holding.average_cost,
        current_price=holding.current_price,
        market_value=market_value,
        unrealized_profit_loss=(holding.current_price - holding.average_cost) * holding.shares,
        contract_capacity=holding.shares // 100,
        active_contracts=active_contracts,
        coverage_percent=_ratio(active_contracts, holding.shares // 100),
        call_tickets=len(symbol_records),
        contracts_sold=contract_count,
        expired_contracts=_contracts(symbol_records, "Expired"),
        closed_contracts=_contracts(symbol_records, "Closed"),
        rolled_contracts=_contracts(symbol_records, "Rolled"),
        assigned_contracts=_contracts(symbol_records, "Assigned"),
        called_away_shares=D(_contracts(symbol_records, "Assigned") * 100),
        gross_premium=gross_premium,
        buyback_cost=sum((record.buyback_cost for record in symbol_records), ZERO),
        net_option_cash=net_option_cash,
        realized_option_income=sum((record.net_cash for record in completed), ZERO),
        open_call_credit=sum((record.gross_premium for record in open_records), ZERO),
        quarter_dividends=holding.quarter_dividends,
        quarter_total_cash=net_option_cash + holding.quarter_dividends,
        quarter_option_apr=(net_option_cash / market_value * annual_factor * 100).quantize(TENTH),
        quarter_total_cash_apr=(
            (net_option_cash + holding.quarter_dividends) / market_value * annual_factor * 100
        ).quantize(TENTH),
        average_open_call_iv_percent=_weighted_average(
            (clock.implied_volatility_percent, clock.contracts)
            for clock in open_call_clocks
            if clock.implied_volatility_percent is not None
        ),
        average_open_call_delta=_weighted_average(
            (abs(clock.delta), clock.contracts)
            for clock in open_call_clocks
            if clock.delta is not None
        ),
        current_strike_buffer_percent=_current_strike_buffer(open_records, holding.current_price),
        next_ex_dividend_date=holding.next_ex_dividend_date,
        dividend_per_share=holding.dividend_per_share,
        dividend_overlap_contracts=_dividend_overlap_contracts(
            open_records, holding.next_ex_dividend_date
        ),
        premium_capture_percent=(net_option_cash / gross_premium * 100).quantize(TENTH),
        lifetime_option_income=holding.lifetime_option_income,
        lifetime_dividends=holding.lifetime_dividends,
        income_adjusted_basis=income_adjusted_basis,
        income_adjusted_basis_per_share=(income_adjusted_basis / holding.shares).quantize(TENTH),
        basis_offset_percent=(lifetime_income / original_cost_basis * 100).quantize(TENTH),
        average_strike_upside_percent=(weighted_upside / contract_count).quantize(TENTH),
        average_days_to_expiration=(D(weighted_dte) / contract_count).quantize(TENTH),
        win_rate=_ratio(sum(1 for record in completed if record.net_cash > ZERO), len(completed)),
        performance_windows=build_name_windows(holding.symbol, market_value),
        open_call_clocks=open_call_clocks,
        thirteen_week_low=min(prices),
        thirteen_week_mid=((min(prices) + max(prices)) / 2).quantize(D("0.01")),
        thirteen_week_high=max(prices),
        thirteen_week_change_percent=((holding.current_price / prices[0] - 1) * HUNDRED).quantize(
            TENTH
        ),
        range_position_percent=(
            (holding.current_price - min(prices)) / (max(prices) - min(prices)) * HUNDRED
        ).quantize(TENTH)
        if max(prices) != min(prices)
        else D("50.0"),
        distance_from_high_percent=((holding.current_price / max(prices) - 1) * HUNDRED).quantize(
            TENTH
        ),
        price_points=price_points,
        price_events=build_price_events(symbol_records, price_points, as_of),
        share_trade_events=build_share_trade_events(
            SHARE_TRADES.get(holding.symbol, ()), price_points
        ),
        tone=holding.tone,
    )


def _current_strike_buffer(records: Sequence[CallSaleRecord], current_price: Decimal) -> Decimal:
    contracts = sum(record.contracts for record in records)
    if not contracts:
        return ZERO
    weighted_strike = (
        sum((record.strike * record.contracts for record in records), ZERO) / contracts
    )
    return ((weighted_strike / current_price - 1) * 100).quantize(TENTH)


def _dividend_overlap_contracts(
    records: Sequence[CallSaleRecord], ex_dividend_date: date | None
) -> int:
    if ex_dividend_date is None:
        return 0
    return sum(record.contracts for record in records if record.expires_on >= ex_dividend_date)


def _contracts(records: Sequence[CallSaleRecord], outcome: str) -> int:
    return sum(record.contracts for record in records if record.outcome == outcome)


def _ratio(numerator: int, denominator: int) -> Decimal:
    return (D(numerator) / D(denominator) * 100).quantize(TENTH) if denominator else ZERO


def _weighted_average(values: Iterable[tuple[Decimal, int]]) -> Decimal | None:
    rows = tuple(values)
    weight = sum((contracts for _, contracts in rows), 0)
    return (
        sum((value * D(contracts) for value, contracts in rows), ZERO) / D(weight)
        if weight
        else None
    )


def _open_call_clock(record: CallSaleRecord, current_price: Decimal, as_of: date) -> OpenCallClock:
    metric = OPEN_CALL_METRICS[(record.symbol, record.expires_on, record.strike)]
    days_to_expiration = max(0, (record.expires_on - as_of).days)
    elapsed_days = min(record.days_to_expiration, max(0, (as_of - record.sold_on).days))
    elapsed_time_percent = (
        D(elapsed_days) / D(record.days_to_expiration) * HUNDRED
        if record.days_to_expiration
        else HUNDRED
    ).quantize(TENTH)
    intrinsic_per_share = max(ZERO, current_price - record.strike)
    strike_distance_per_share = record.strike - current_price
    extrinsic_per_share = max(ZERO, metric.mark_per_share - intrinsic_per_share)
    remaining_extrinsic = extrinsic_per_share * record.contracts * 100
    intrinsic_value = intrinsic_per_share * record.contracts * 100
    current_option_value = metric.mark_per_share * record.contracts * 100
    open_profit_loss = record.gross_premium - current_option_value
    short_theta_per_day = -metric.theta_per_share * record.contracts * 100
    return OpenCallClock(
        record_id=record.record_id,
        campaign_id=record.campaign_id,
        campaign_label="",
        policy_id=record.policy_id,
        sold_on=record.sold_on,
        expires_on=record.expires_on,
        strike=record.strike,
        contracts=record.contracts,
        underlying_at_sale=record.underlying_at_sale,
        close_ask_per_share=metric.ask_per_share,
        bid_per_share=metric.bid_per_share,
        spread_per_share=metric.ask_per_share - metric.bid_per_share,
        spread_percent_of_mark=(
            (metric.ask_per_share - metric.bid_per_share) / metric.mark_per_share * HUNDRED
        ).quantize(TENTH),
        quote_observed_on=as_of,
        quote_status="SIMULATED",
        implied_volatility_percent=metric.implied_volatility_percent,
        delta=metric.delta,
        gamma=metric.gamma,
        vega=metric.vega,
        volume=metric.volume,
        open_interest=metric.open_interest,
        roll_quote_candidates=ROLL_QUOTE_CANDIDATES.get(
            (record.symbol, record.expires_on, record.strike), ()
        ),
        original_days_to_expiration=record.days_to_expiration,
        elapsed_days=elapsed_days,
        elapsed_time_percent=elapsed_time_percent,
        days_to_expiration=days_to_expiration,
        strike_distance_per_share=strike_distance_per_share,
        strike_distance_percent=(strike_distance_per_share / current_price * HUNDRED).quantize(
            TENTH
        ),
        mark_per_share=metric.mark_per_share,
        entry_credit_per_share=record.premium_per_share,
        entry_credit=record.gross_premium,
        current_option_value=current_option_value,
        open_profit_loss=open_profit_loss,
        credit_capture_percent=(open_profit_loss / record.gross_premium * HUNDRED).quantize(TENTH),
        option_value_vs_credit_percent=(
            current_option_value / record.gross_premium * HUNDRED
        ).quantize(TENTH),
        intrinsic_value=intrinsic_value,
        remaining_extrinsic_value=remaining_extrinsic,
        theta_per_share=metric.theta_per_share,
        short_theta_per_day=short_theta_per_day,
        theta_decay_percent_of_extrinsic=(short_theta_per_day / remaining_extrinsic * 100).quantize(
            TENTH
        )
        if remaining_extrinsic
        else ZERO,
        theta_days_of_time_value=(remaining_extrinsic / short_theta_per_day).quantize(TENTH)
        if short_theta_per_day
        else ZERO,
        time_remaining_percent=(HUNDRED - elapsed_time_percent).quantize(TENTH),
        decay_stage=_decay_stage(days_to_expiration),
    )


def _decay_stage(days_to_expiration: int) -> str:
    if days_to_expiration <= 20:
        return "EXPIRY ZONE"
    if days_to_expiration <= 35:
        return "DECAY BUILDING"
    return "EARLY CYCLE"


def _required_decimal(value: Decimal | None) -> Decimal:
    """Narrow price context guaranteed by the fictional demo fixtures."""

    if value is None:
        raise ValueError("demo call history requires complete price context")
    return value
