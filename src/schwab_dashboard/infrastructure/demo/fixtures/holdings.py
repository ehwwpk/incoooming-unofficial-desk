from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
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
    lifetime_option_income: Decimal
    lifetime_dividends: Decimal
    tone: str
    weekly_prices: Sequence[tuple[str, str, bool]]


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
        lifetime_option_income=D("9850.00"),
        lifetime_dividends=D("7420.00"),
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
        quarter_dividends=D("0"),
        average_open_call_iv_percent=D("58.6"),
        average_open_call_delta=D("0.22"),
        lifetime_option_income=D("11720.00"),
        lifetime_dividends=D("0"),
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
        quarter_dividends=D("0"),
        average_open_call_iv_percent=D("41.2"),
        average_open_call_delta=D("0.20"),
        lifetime_option_income=D("6850.00"),
        lifetime_dividends=D("2130.00"),
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
