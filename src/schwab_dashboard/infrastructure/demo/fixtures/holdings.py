from __future__ import annotations

from collections.abc import Sequence
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
    average_open_call_iv_percent: Decimal
    average_open_call_delta: Decimal
    next_ex_dividend_date: date | None
    dividend_per_share: Decimal
    lifetime_option_income: Decimal
    lifetime_dividends: Decimal
    tone: str
    weekly_closes: Sequence[tuple[str, str]]


HOLDINGS = (
    HoldingFixture(
        symbol="CVX",
        company_name="Chevron",
        shares=700,
        average_cost=D("155.40"),
        current_price=D("192.26"),
        quarter_dividends=D("1246.00"),
        average_open_call_iv_percent=D("23.8"),
        average_open_call_delta=D("0.18"),
        next_ex_dividend_date=date(2026, 8, 19),
        dividend_per_share=D("1.78"),
        lifetime_option_income=D("9850.00"),
        lifetime_dividends=D("7420.00"),
        tone="gold",
        weekly_closes=(
            ("05/15", "181.00"),
            ("05/22", "191.43"),
            ("05/29", "182.46"),
            ("06/05", "187.55"),
            ("06/12", "180.20"),
            ("06/19", "173.63"),
            ("06/26", "171.06"),
            ("07/03", "169.20"),
            ("07/10", "176.40"),
            ("07/17", "187.38"),
            ("07/24", "194.79"),
            ("07/31", "190.00"),
            ("08/07", "192.26"),
        ),
    ),
    HoldingFixture(
        symbol="KTOS",
        company_name="Kratos Defense",
        shares=800,
        average_cost=D("31.75"),
        current_price=D("65.19"),
        quarter_dividends=D("0"),
        average_open_call_iv_percent=D("58.6"),
        average_open_call_delta=D("0.22"),
        next_ex_dividend_date=None,
        dividend_per_share=D("0"),
        lifetime_option_income=D("11720.00"),
        lifetime_dividends=D("0"),
        tone="emerald",
        weekly_closes=(
            ("05/15", "38.60"),
            ("05/22", "40.20"),
            ("05/29", "42.10"),
            ("06/05", "44.70"),
            ("06/12", "45.30"),
            ("06/19", "44.90"),
            ("06/26", "46.80"),
            ("07/03", "48.60"),
            ("07/10", "50.36"),
            ("07/17", "48.90"),
            ("07/24", "52.40"),
            ("07/31", "56.50"),
            ("08/07", "65.19"),
        ),
    ),
    HoldingFixture(
        symbol="URNM",
        company_name="Sprott Uranium Miners ETF",
        shares=500,
        average_cost=D("44.20"),
        current_price=D("54.57"),
        quarter_dividends=D("0"),
        average_open_call_iv_percent=D("41.2"),
        average_open_call_delta=D("0.20"),
        next_ex_dividend_date=None,
        dividend_per_share=D("0"),
        lifetime_option_income=D("6850.00"),
        lifetime_dividends=D("2130.00"),
        tone="olive",
        weekly_closes=(
            ("05/15", "47.20"),
            ("05/22", "47.80"),
            ("05/29", "49.10"),
            ("06/05", "50.60"),
            ("06/12", "50.10"),
            ("06/19", "51.40"),
            ("06/26", "52.40"),
            ("07/03", "53.20"),
            ("07/10", "56.20"),
            ("07/17", "55.10"),
            ("07/24", "53.30"),
            ("07/31", "53.80"),
            ("08/07", "54.57"),
        ),
    ),
)
