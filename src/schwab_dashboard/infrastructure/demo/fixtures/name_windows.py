from __future__ import annotations

from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import UnderlyingPerformanceWindow

D = Decimal
ZERO = D("0")
TENTH = D("0.1")
YEAR_DAYS = D("365")

WINDOW_DAYS = {
    "week": 7,
    "month": 28,
    "quarter": 85,
    "ytd": 219,
    "r365": 365,
}

# key, option cash, dividends, gross premium, buy-to-close cost
NAME_WINDOW_ROWS = {
    "CVX": (
        ("week", "0", "0", "0", "0"),
        ("month", "300", "0", "1200", "900"),
        ("quarter", "2275", "1246", "2825", "550"),
        ("ytd", "8000", "2700", "11000", "3000"),
        ("r365", "12000", "4100", "17500", "5500"),
    ),
    "KTOS": (
        ("week", "-185", "0", "465", "650"),
        ("month", "490", "0", "1690", "1200"),
        ("quarter", "2370", "0", "4345", "1975"),
        ("ytd", "8200", "0", "12500", "4300"),
        ("r365", "11700", "0", "18000", "6300"),
    ),
    "URNM": (
        ("week", "80", "0", "500", "420"),
        ("month", "225", "0", "500", "275"),
        ("quarter", "1695", "0", "1835", "140"),
        ("ytd", "5680", "716", "8450", "2770"),
        ("r365", "8080", "1136", "12750", "4670"),
    ),
}


def build_name_windows(
    symbol: str, market_value: Decimal
) -> tuple[UnderlyingPerformanceWindow, ...]:
    return tuple(_window(row, market_value) for row in NAME_WINDOW_ROWS[symbol])


def _window(
    row: tuple[str, str, str, str, str], market_value: Decimal
) -> UnderlyingPerformanceWindow:
    key, option, dividend, gross, buyback = row
    days = WINDOW_DAYS[key]
    option_cash = D(option)
    dividends = D(dividend)
    gross_premium = D(gross)
    buyback_cost = D(buyback)
    annual_factor = YEAR_DAYS / D(days)
    return UnderlyingPerformanceWindow(
        key=key,
        option_cash=option_cash,
        dividends=dividends,
        total_cash=option_cash + dividends,
        gross_premium=gross_premium,
        buyback_cost=buyback_cost,
        option_apr=(option_cash / market_value * annual_factor * 100).quantize(TENTH),
        total_cash_apr=((option_cash + dividends) / market_value * annual_factor * 100).quantize(
            TENTH
        ),
        premium_capture_percent=(option_cash / gross_premium * 100).quantize(TENTH)
        if gross_premium
        else ZERO,
    )
