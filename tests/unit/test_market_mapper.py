from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from schwab_dashboard.domain.market import MarkMethod, QuoteQuality
from schwab_dashboard.infrastructure.schwab.market_mapper import SchwabMarketMapper

NOW = datetime(2026, 8, 11, 18, tzinfo=UTC)


def test_maps_underlying_quote_with_source_timestamp() -> None:
    batch = SchwabMarketMapper().map_quotes(
        {
            "KTOS": {
                "symbol": "KTOS",
                "assetMainType": "EQUITY",
                "quote": {
                    "bidPrice": 60.7,
                    "askPrice": 60.8,
                    "lastPrice": 60.75,
                    "mark": 60.75,
                    "closePrice": 59,
                    "quoteTime": 1786471140000,
                },
                "reference": {"description": "Kratos Defense"},
            }
        },
        observed_at=NOW,
        parser_version="test",
    )

    snapshot = batch.underlying_snapshots[0]
    assert snapshot.quote_quality is QuoteQuality.COMPLETE
    assert snapshot.mark_method is MarkMethod.BROKER
    assert snapshot.mark == Decimal("60.75")
    assert snapshot.observed_at <= batch.observed_at


def test_maps_only_requested_open_call_with_greeks() -> None:
    symbol = "KTOS  260918C00075000"
    batch = SchwabMarketMapper().map_chain(
        {
            "symbol": "KTOS",
            "underlyingPrice": 60.75,
            "callExpDateMap": {
                "2026-09-18:38": {
                    "75.0": [
                        {
                            "symbol": symbol,
                            "description": "KTOS Sep 18 2026 75 Call",
                            "putCall": "CALL",
                            "strikePrice": 75,
                            "multiplier": 100,
                            "bid": 1.2,
                            "ask": 1.4,
                            "mark": 1.3,
                            "last": 1.25,
                            "volatility": 58.6,
                            "delta": 0.25,
                            "gamma": 0.03,
                            "theta": -0.04,
                            "vega": 0.08,
                            "rho": 0.01,
                            "totalVolume": 20,
                            "openInterest": 400,
                            "quoteTimeInLong": 1786471140000,
                            "nonStandard": False,
                        }
                    ],
                    "80.0": [{"symbol": "KTOS  260918C00080000"}],
                }
            },
        },
        observed_at=NOW,
        parser_version="test",
        open_option_symbols=[symbol],
    )

    assert len(batch.option_snapshots) == 1
    snapshot = batch.option_snapshots[0]
    assert snapshot.implied_volatility == Decimal("58.6")
    assert snapshot.delta == Decimal("0.25")
    assert snapshot.theta == Decimal("-0.04")
    assert snapshot.open_interest == 400


def test_maps_real_daily_ohlcv_bars() -> None:
    batch = SchwabMarketMapper().map_price_history(
        {
            "symbol": "KTOS",
            "candles": [
                {
                    "datetime": 1786406400000,
                    "open": 59,
                    "high": 61,
                    "low": 58.5,
                    "close": 60.75,
                    "volume": 1000,
                }
            ],
        },
        observed_at=NOW,
        parser_version="test",
    )

    assert len(batch.daily_bars) == 1
    assert batch.daily_bars[0].close == Decimal("60.75")
    assert batch.daily_bars[0].volume == 1000
