from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

from schwab_dashboard.application.services.sync_market import (
    SyncSchwabMarketData,
    _held_market_assets,
    _history_symbols,
)
from schwab_dashboard.domain.instruments import AssetType
from schwab_dashboard.domain.market import MarketObservationBatch
from schwab_dashboard.infrastructure.schwab.market_mapper import SchwabMarketMapper


def test_history_selection_covers_whole_market_book_and_reference() -> None:
    assets = _held_market_assets(
        (
            {"symbol": "CVX", "asset_type": "EQUITY"},
            {"symbol": "URNM", "asset_type": "ETF"},
            {"symbol": "NEE", "asset_type": "EQUITY"},
            {"symbol": "KTOS  260814C00068000", "asset_type": "OPTION"},
            {"symbol": "CASH", "asset_type": "CASH"},
        )
    )

    assert assets == {
        "CVX": AssetType.EQUITY,
        "NEE": AssetType.EQUITY,
        "URNM": AssetType.ETF,
    }
    assert _history_symbols(sorted(assets)) == ["CVX", "NEE", "SPY", "URNM"]


def test_sync_refreshes_short_calls_puts_all_holdings_and_spy() -> None:
    positions = (
        {"symbol": "CVX", "asset_type": "EQUITY"},
        {"symbol": "NEE", "asset_type": "EQUITY"},
        {
            "symbol": "CVX  260821C00200000",
            "asset_type": "OPTION",
            "option_type": "CALL",
            "short_quantity": 1,
            "underlying_symbol": "CVX",
            "expiration_date": date(2026, 8, 21),
        },
        {
            "symbol": "NEE  260821P00080000",
            "asset_type": "OPTION",
            "option_type": "PUT",
            "short_quantity": 1,
            "underlying_symbol": "NEE",
            "expiration_date": date(2026, 8, 21),
        },
    )
    client = _MarketClient()
    service = SyncSchwabMarketData(
        client=client,  # type: ignore[arg-type]
        mapper=SchwabMarketMapper(),
        recorder=_Recorder(),  # type: ignore[arg-type]
        uow_factory=lambda: _Uow(positions),  # type: ignore[arg-type]
        parser_version="test",
    )

    service.execute()

    assert client.chain_calls == [("CVX", "ALL"), ("NEE", "ALL")]
    assert client.history_calls == ["CVX", "NEE", "SPY"]
    assert client.intraday_calls == ["CVX", "NEE"]


class _Uow:
    def __init__(self, positions: tuple[dict[str, object], ...]) -> None:
        self.positions = SimpleNamespace(list_latest=lambda: positions)

    def __enter__(self) -> _Uow:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _Recorder:
    def execute(self, batch: MarketObservationBatch) -> SimpleNamespace:
        return SimpleNamespace(
            underlying_snapshot_count=len(batch.underlying_snapshots),
            option_snapshot_count=len(batch.option_snapshots),
        )


class _MarketClient:
    def __init__(self) -> None:
        self.chain_calls: list[tuple[str, str]] = []
        self.history_calls: list[str] = []
        self.intraday_calls: list[str] = []

    def get_quotes(self, symbols: list[str]) -> dict[str, object]:
        assert symbols == ["CVX", "NEE"]
        return {}

    def get_option_chain(self, symbol: str, **kwargs: object) -> dict[str, object]:
        self.chain_calls.append((symbol, str(kwargs["contract_type"])))
        return {"symbol": symbol, "callExpDateMap": {}, "putExpDateMap": {}}

    def get_daily_price_history(self, symbol: str) -> dict[str, object]:
        self.history_calls.append(symbol)
        return {"symbol": symbol, "candles": []}

    def get_intraday_price_history(
        self,
        symbol: str,
        *,
        start_at: datetime,
        end_at: datetime,
        frequency_minutes: int,
    ) -> dict[str, object]:
        assert start_at < end_at
        assert frequency_minutes == 30
        self.intraday_calls.append(symbol)
        return {"symbol": symbol, "candles": []}
