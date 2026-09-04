from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

D = Decimal


@dataclass(frozen=True, slots=True)
class HoldingFixture:
    symbol: str
    company_name: str
    shares: int
    average_cost: Decimal
    current_price: Decimal
    quarter_dividends: Decimal
    next_ex_dividend_date: date | None
    dividend_per_share: Decimal
    lifetime_option_income: Decimal
    lifetime_dividends: Decimal
    tone: str


HOLDINGS = (
    HoldingFixture(
        symbol="CVX",
        company_name="Chevron",
        shares=700,
        average_cost=D("155.40"),
        current_price=D("186.56"),
        quarter_dividends=D("1246.00"),
        next_ex_dividend_date=date(2026, 8, 19),
        dividend_per_share=D("1.78"),
        lifetime_option_income=D("9850.00"),
        lifetime_dividends=D("7420.00"),
        tone="gold",
    ),
    HoldingFixture(
        symbol="KTOS",
        company_name="Kratos Defense",
        shares=800,
        average_cost=D("31.75"),
        current_price=D("60.77"),
        quarter_dividends=D("0"),
        next_ex_dividend_date=None,
        dividend_per_share=D("0"),
        lifetime_option_income=D("11720.00"),
        lifetime_dividends=D("0"),
        tone="emerald",
    ),
    HoldingFixture(
        symbol="URNM",
        company_name="Sprott Uranium Miners ETF",
        shares=500,
        average_cost=D("44.20"),
        current_price=D("54.53"),
        quarter_dividends=D("0"),
        next_ex_dividend_date=None,
        dividend_per_share=D("0"),
        lifetime_option_income=D("6850.00"),
        lifetime_dividends=D("2130.00"),
        tone="olive",
    ),
)
