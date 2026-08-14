from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from schwab_dashboard.domain.instruments import AssetType, OptionSide
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


def test_maps_etf_underlying_without_downgrading_it_to_unknown() -> None:
    batch = SchwabMarketMapper().map_quotes(
        {
            "URNM": {
                "symbol": "URNM",
                "assetMainType": "EQUITY",
                "assetSubType": "ETF",
                "quote": {
                    "bidPrice": 55.35,
                    "askPrice": 55.40,
                    "mark": 55.375,
                    "quoteTime": 1786471140000,
                },
                "reference": {"description": "Sprott Uranium Miners ETF"},
            }
        },
        observed_at=NOW,
        parser_version="test",
    )

    assert batch.instruments[0].asset_type is AssetType.ETF
    assert batch.instruments[0].symbol == "URNM"
    assert batch.underlying_snapshots[0].mark == Decimal("55.375")


def test_clamps_provider_quote_clock_skew_to_the_raw_event_time() -> None:
    future_quote_time = int((NOW + timedelta(seconds=3)).timestamp() * 1000)
    batch = SchwabMarketMapper().map_quotes(
        {
            "CVX": {
                "symbol": "CVX",
                "assetMainType": "EQUITY",
                "quote": {"mark": 198.25, "quoteTime": future_quote_time},
            }
        },
        observed_at=NOW,
        parser_version="test",
    )

    assert batch.underlying_snapshots[0].observed_at == batch.observed_at


def test_maps_open_call_and_replacement_chain_quotes_with_greeks() -> None:
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
    )

    assert len(batch.option_snapshots) == 2
    snapshot = batch.option_snapshots[0]
    assert snapshot.implied_volatility == Decimal("58.6")
    assert snapshot.delta == Decimal("0.25")
    assert snapshot.theta == Decimal("-0.04")
    assert snapshot.open_interest == 400


def test_maps_put_chain_without_relabelling_it_as_a_call() -> None:
    symbol = "URNM  260918P00050000"
    batch = SchwabMarketMapper().map_chain(
        {
            "symbol": "URNM",
            "underlyingPrice": 55.37,
            "putExpDateMap": {
                "2026-09-18:38": {
                    "50.0": [
                        {
                            "symbol": symbol,
                            "putCall": "PUT",
                            "strikePrice": 50,
                            "multiplier": 100,
                            "bid": 0.9,
                            "ask": 1.05,
                            "volatility": 46,
                            "delta": -0.22,
                            "quoteTimeInLong": 1786471140000,
                        }
                    ]
                }
            },
        },
        observed_at=NOW,
        parser_version="test",
    )

    assert len(batch.instruments) == 1
    assert len(batch.option_snapshots) == 1
    assert batch.instruments[0].option_side is OptionSide.PUT
    assert batch.instruments[0].underlying_symbol == "URNM"
    assert batch.option_snapshots[0].delta == Decimal("-0.22")


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


def test_maps_timestamped_intraday_ohlcv_bars() -> None:
    batch = SchwabMarketMapper().map_intraday_price_history(
        {
            "symbol": "CVX",
            "candles": [
                {
                    "datetime": 1786469400000,
                    "open": 195,
                    "high": 197,
                    "low": 194.5,
                    "close": 196.25,
                    "volume": 1200,
                }
            ],
        },
        observed_at=NOW,
        parser_version="test",
        interval_minutes=30,
    )

    assert len(batch.intraday_bars) == 1
    assert batch.intraday_bars[0].interval_minutes == 30
    assert batch.intraday_bars[0].started_at.tzinfo is not None
    assert batch.intraday_bars[0].close == Decimal("196.25")


def test_intraday_mapper_keeps_the_last_revision_for_duplicate_time_buckets() -> None:
    batch = SchwabMarketMapper().map_intraday_price_history(
        {
            "symbol": "CVX",
            "candles": [
                {
                    "datetime": 1786469400000,
                    "open": 195,
                    "high": 197,
                    "low": 194.5,
                    "close": 196.25,
                    "volume": 1200,
                },
                {
                    "datetime": 1786469400000,
                    "open": 195,
                    "high": 197.5,
                    "low": 194.5,
                    "close": 196.5,
                    "volume": 1350,
                },
            ],
        },
        observed_at=NOW,
        parser_version="test",
        interval_minutes=30,
    )

    assert len(batch.intraday_bars) == 1
    assert batch.intraday_bars[0].close == Decimal("196.5")
    assert batch.intraday_bars[0].volume == 1350


def test_price_history_preserves_known_asset_type() -> None:
    batch = SchwabMarketMapper().map_price_history(
        {
            "symbol": "URNM",
            "candles": [
                {
                    "datetime": 1786406400000,
                    "open": 54,
                    "high": 56,
                    "low": 53,
                    "close": 55,
                    "volume": 1000,
                }
            ],
        },
        observed_at=NOW,
        parser_version="test",
        asset_type=AssetType.ETF,
    )

    assert batch.instruments[0].asset_type is AssetType.ETF
