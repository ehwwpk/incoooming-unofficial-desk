from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.rolls.collect import collect_roll_quotes
from schwab_dashboard.domain.instruments import OptionSide

D = Decimal
NOW = datetime(2026, 8, 17, 20, tzinfo=UTC)


def test_collect_roll_quotes_keeps_later_higher_calls_and_skips_the_source() -> None:
    quotes = collect_roll_quotes(
        underlying_symbol="CVX",
        option_side=OptionSide.CALL,
        source_expiration=date(2026, 8, 21),
        source_strike=D("210"),
        source_option_symbol="CVX  260821C00210000",
        option_market=(
            _row("CVX", "CVX  260821C00210000", date(2026, 8, 21), "210", "0.28", "call"),
            _row("CVX", "CVX  260828C00215000", date(2026, 8, 28), "215", "0.25", "call"),
            _row("CVX", "CVX  260828C00210000", date(2026, 8, 28), "210", "0.40", "call"),
            _row("CVX", "CVX  260828P00215000", date(2026, 8, 28), "215", "1.10", "put"),
            _row("KTOS", "KTOS 260828C00080000", date(2026, 8, 28), "80", "0.90", "call"),
            _row("CVX", "CVX  260828C00212500", date(2026, 8, 28), "212.50", "0", "call"),
        ),
    )

    assert [item.option_symbol for item in quotes] == ["CVX  260828C00215000"]
    assert quotes[0].sell_bid_per_share == D("0.25")
    assert quotes[0].theta_per_share == D("-0.04")


def test_collect_roll_quotes_allows_same_or_lower_puts() -> None:
    quotes = collect_roll_quotes(
        underlying_symbol="XYZ",
        option_side="PUT",
        source_expiration=date(2026, 8, 21),
        source_strike=D("50"),
        option_market=(
            _row("XYZ", "XYZ PUT 50", date(2026, 8, 28), "50", "1.00", "put"),
            _row("XYZ", "XYZ PUT 45", date(2026, 8, 28), "45", "0.80", "put"),
            _row("XYZ", "XYZ PUT 55", date(2026, 8, 28), "55", "1.40", "put"),
        ),
    )

    assert [item.strike for item in quotes] == [D("45"), D("50")]


def _row(
    underlying: str,
    symbol: str,
    expiration: date,
    strike: str,
    bid: str,
    side: str,
) -> dict[str, object]:
    return {
        "underlying_symbol": underlying,
        "symbol": symbol,
        "expiration_date": expiration,
        "strike": D(strike),
        "bid": D(bid),
        "ask": D(bid) + D("0.05") if D(bid) else D("0.05"),
        "mark": D(bid) + D("0.02") if D(bid) else D("0.02"),
        "option_side": side,
        "quote_quality": "complete",
        "open_interest": 100,
        "volume": 10,
        "theta": D("-0.04"),
        "observed_at": NOW,
    }
