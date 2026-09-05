from __future__ import annotations

from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import UnderlyingPerformanceWindow
from schwab_dashboard.infrastructure.demo.fixtures.short_puts import build_put_cash_events

D = Decimal
ZERO = D("0")
TENTH = D("0.1")
YEAR_DAYS = D("365")

WINDOW_DAYS = {
    "month": 28,
    "quarter": 85,
    "ytd": 219,
    "r365": 365,
}

# key, option cash, dividends, gross premium, buy-to-close cost
NAME_WINDOW_ROWS = {
    "CVX": (
        ("month", "720", "0", "1200", "480"),
        ("quarter", "2275", "1246", "2825", "550"),
        ("ytd", "6275", "2443", "8275", "2000"),
        ("r365", "9775", "4033", "13050", "3275"),
    ),
    "KTOS": (
        ("month", "445", "0", "2260", "1815"),
        ("quarter", "2370", "0", "4345", "1975"),
        ("ytd", "6370", "0", "8170", "1800"),
        ("r365", "9870", "0", "13170", "3300"),
    ),
    "URNM": (
        ("month", "640", "0", "780", "140"),
        ("quarter", "1695", "0", "1835", "140"),
        ("ytd", "3695", "0", "4560", "865"),
        ("r365", "6490", "0", "8885", "2395"),
    ),
}


def build_name_windows(
    symbol: str, market_value: Decimal
) -> tuple[UnderlyingPerformanceWindow, ...]:
    # Both fictional put openings fall inside every displayed window (Aug 3/4).
    put_credit = sum(
        (event.amount for event in build_put_cash_events() if event.symbol == symbol), ZERO
    )
    return tuple(_window(row, market_value, put_credit) for row in NAME_WINDOW_ROWS[symbol])


def _window(
    row: tuple[str, str, str, str, str], market_value: Decimal, put_credit: Decimal
) -> UnderlyingPerformanceWindow:
    key, option, dividend, gross, buyback = row
    days = WINDOW_DAYS[key]
    option_cash = D(option) + put_credit
    dividends = D(dividend)
    gross_premium = D(gross) + put_credit
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
