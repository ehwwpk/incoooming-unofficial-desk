from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import (
    CallSaleRecord,
    CoveredCallPortfolioSummary,
    PricePoint,
    UnderlyingCallStats,
)

D = Decimal
ZERO = D("0")
TENTH = D("0.1")


@dataclass(frozen=True, slots=True)
class HoldingFixture:
    symbol: str
    company_name: str
    shares: int
    average_cost: Decimal
    current_price: Decimal
    tone: str
    weekly_prices: Sequence[tuple[str, str, bool]]


HOLDINGS = (
    HoldingFixture(
        symbol="CVX",
        company_name="Chevron",
        shares=700,
        average_cost=D("155.40"),
        current_price=D("192.26"),
        tone="amber",
        weekly_prices=(
            ("05/15", "181.00", True),
            ("05/22", "191.43", True),
            ("05/29", "182.46", False),
            ("06/05", "187.55", False),
            ("06/12", "180.20", False),
            ("06/19", "173.63", False),
            ("06/26", "171.06", False),
            ("07/03", "169.20", False),
            ("07/10", "176.40", True),
            ("07/17", "187.38", False),
            ("07/24", "194.79", True),
            ("07/31", "190.00", True),
            ("08/07", "192.26", False),
        ),
    ),
    HoldingFixture(
        symbol="KTOS",
        company_name="Kratos Defense",
        shares=800,
        average_cost=D("31.75"),
        current_price=D("65.19"),
        tone="cyan",
        weekly_prices=(
            ("05/15", "38.60", True),
            ("05/22", "40.20", False),
            ("05/29", "42.10", True),
            ("06/05", "44.70", False),
            ("06/12", "45.30", False),
            ("06/19", "44.90", False),
            ("06/26", "46.80", True),
            ("07/03", "48.60", False),
            ("07/10", "50.36", True),
            ("07/17", "48.90", False),
            ("07/24", "52.40", False),
            ("07/31", "56.50", True),
            ("08/07", "65.19", True),
        ),
    ),
    HoldingFixture(
        symbol="URNM",
        company_name="Sprott Uranium Miners ETF",
        shares=500,
        average_cost=D("44.20"),
        current_price=D("54.57"),
        tone="violet",
        weekly_prices=(
            ("05/15", "47.20", False),
            ("05/22", "47.80", True),
            ("05/29", "49.10", False),
            ("06/05", "50.60", True),
            ("06/12", "50.10", False),
            ("06/19", "51.40", False),
            ("06/26", "52.40", True),
            ("07/03", "53.20", False),
            ("07/10", "56.20", True),
            ("07/17", "55.10", False),
            ("07/24", "53.30", False),
            ("07/31", "53.80", False),
            ("08/07", "54.57", True),
        ),
    ),
)


def build_underlying_stats(
    records: Sequence[CallSaleRecord],
) -> tuple[UnderlyingCallStats, ...]:
    return tuple(_summarize_holding(holding, records) for holding in HOLDINGS)


def build_covered_call_summary(
    records: Sequence[CallSaleRecord],
    underlyings: Sequence[UnderlyingCallStats],
) -> CoveredCallPortfolioSummary:
    completed = [record for record in records if record.outcome != "Open"]
    wins = sum(1 for record in completed if record.net_cash > ZERO)
    stock_value = sum((underlying.market_value for underlying in underlyings), ZERO)
    net_option_cash = sum((record.net_cash for record in records), ZERO)
    dividends = D("1246.00")
    return CoveredCallPortfolioSummary(
        total_shares=sum(item.shares for item in underlyings),
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
        called_away_shares=_contracts(records, "Assigned") * 100,
        gross_premium=sum((record.gross_premium for record in records), ZERO),
        buyback_cost=sum((record.buyback_cost for record in records), ZERO),
        net_option_cash=net_option_cash,
        realized_option_income=sum((record.net_cash for record in completed), ZERO),
        open_call_credit=sum(
            (record.gross_premium for record in records if record.outcome == "Open"), ZERO
        ),
        dividends=dividends,
        total_cash_income=net_option_cash + dividends,
        win_rate=_ratio(wins, len(completed)),
        annualized_option_yield=(net_option_cash / stock_value * 400).quantize(TENTH),
    )


def _summarize_holding(
    holding: HoldingFixture,
    records: Sequence[CallSaleRecord],
) -> UnderlyingCallStats:
    symbol_records = [record for record in records if record.symbol == holding.symbol]
    completed = [record for record in symbol_records if record.outcome != "Open"]
    open_records = [record for record in symbol_records if record.outcome == "Open"]
    contract_count = sum(record.contracts for record in symbol_records)
    active_contracts = sum(record.contracts for record in open_records)
    market_value = holding.current_price * holding.shares
    realized = sum((record.net_cash for record in completed), ZERO)
    weighted_upside = sum(
        (record.strike_upside_percent * record.contracts for record in symbol_records), ZERO
    )
    weighted_dte = sum(record.days_to_expiration * record.contracts for record in symbol_records)
    return UnderlyingCallStats(
        symbol=holding.symbol,
        company_name=holding.company_name,
        shares=holding.shares,
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
        called_away_shares=_contracts(symbol_records, "Assigned") * 100,
        gross_premium=sum((record.gross_premium for record in symbol_records), ZERO),
        buyback_cost=sum((record.buyback_cost for record in symbol_records), ZERO),
        net_option_cash=sum((record.net_cash for record in symbol_records), ZERO),
        realized_option_income=realized,
        open_call_credit=sum((record.gross_premium for record in open_records), ZERO),
        average_strike_upside_percent=(weighted_upside / contract_count).quantize(TENTH),
        average_days_to_expiration=(D(weighted_dte) / contract_count).quantize(TENTH),
        win_rate=_ratio(sum(1 for record in completed if record.net_cash > ZERO), len(completed)),
        current_calls=tuple(_call_label(record) for record in open_records),
        price_points=_price_points(holding.weekly_prices),
        tone=holding.tone,
    )


def _price_points(rows: Sequence[tuple[str, str, bool]]) -> tuple[PricePoint, ...]:
    prices = [D(row[1]) for row in rows]
    low = min(prices)
    spread = max(prices) - low
    return tuple(
        PricePoint(
            label=label,
            price=D(price),
            height_percent=(50 if not spread else 15 + int((D(price) - low) / spread * 85)),
            call_sale=call_sale,
        )
        for label, price, call_sale in rows
    )


def _contracts(records: Sequence[CallSaleRecord], outcome: str) -> int:
    return sum(record.contracts for record in records if record.outcome == outcome)


def _ratio(numerator: int, denominator: int) -> Decimal:
    return (D(numerator) / D(denominator) * 100).quantize(TENTH) if denominator else ZERO


def _call_label(record: CallSaleRecord) -> str:
    strike = f"{record.strike:f}".rstrip("0").rstrip(".")
    return f"-{record.contracts} {record.expires_on:%b %d} ${strike}C"
