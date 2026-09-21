from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import httpx
from alembic import command

from schwab_dashboard.app import create_app
from schwab_dashboard.application.services.record_market_observations import (
    RecordMarketObservations,
)
from schwab_dashboard.application.services.sync_accounts import SyncAccountsAndPositions
from schwab_dashboard.cli import _alembic_config
from schwab_dashboard.config import Settings
from schwab_dashboard.container import Container
from schwab_dashboard.domain.instruments import AssetType, InstrumentRecord
from schwab_dashboard.domain.market import InstrumentRef, MarketObservationBatch, UnderlyingDailyBar
from schwab_dashboard.infrastructure.database.uow_market import build_market_uow_factory
from schwab_dashboard.infrastructure.schwab.mapper import SchwabAccountMapper
from tests.fakes import FakeBrokerGateway


def test_sunday_reconnect_reaches_every_results_period_from_stored_broker_data(
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        auto_sync_enabled=False,
        token_service_name="incoooming-test-results-reconnect",
    )
    command.upgrade(_alembic_config(settings), "head")
    container = Container(settings)
    try:
        for stamp, value in (
            (datetime(2026, 9, 10, 21, tzinfo=UTC), 10000),
            (datetime(2026, 9, 21, 2, tzinfo=UTC), 10600),
        ):
            records = SchwabAccountMapper().map_records(
                [{"accountNumber": "fixture-account", "hashValue": "fixture-account-key"}],
                [
                    {
                        "securitiesAccount": {
                            "accountNumber": "fixture-account",
                            "type": "CASH",
                            "currentBalances": {
                                "liquidationValue": value + 5000,
                                "cashBalance": 5000,
                            },
                            "positions": [
                                {
                                    "longQuantity": 100,
                                    "shortQuantity": 0,
                                    "averagePrice": 100,
                                    "marketValue": value,
                                    "instrument": {
                                        "assetType": "COLLECTIVE_INVESTMENT",
                                        "type": "EXCHANGE_TRADED_FUND",
                                        "symbol": "TESTETF",
                                        "cusip": "fixture-etf",
                                    },
                                }
                            ],
                        }
                    }
                ],
            )
            with patch("schwab_dashboard.application.services.sync_accounts.datetime") as clock:
                clock.now.return_value = stamp
                SyncAccountsAndPositions(
                    broker=FakeBrokerGateway(records),
                    uow_factory=container.uow_factory,
                    parser_version="reconnect-test-v1",
                ).execute()
        observed = datetime(2026, 9, 21, 2, tzinfo=UTC)
        RecordMarketObservations(
            uow_factory=build_market_uow_factory(container.session_factory),
        ).execute(
            MarketObservationBatch(
                source="schwab",
                external_event_key="reconnect-prices",
                observed_at=observed,
                parser_version="reconnect-test-v1",
                raw_payload={"fixture": True},
                instruments=tuple(
                    InstrumentRecord(
                        source="schwab",
                        external_key=symbol,
                        symbol=symbol,
                        asset_type=AssetType.ETF,
                        observed_at=observed,
                    )
                    for symbol in ("TESTETF", "SPY")
                ),
                daily_bars=tuple(
                    UnderlyingDailyBar(
                        instrument=InstrumentRef("schwab", symbol),
                        trade_date=date(2026, 9, day),
                        open=Decimal(100 + i),
                        high=Decimal(100 + i),
                        low=Decimal(100 + i),
                        close=Decimal(100 + i),
                        volume=100,
                    )
                    for symbol in ("TESTETF", "SPY")
                    for i, day in enumerate((10, 11, 14, 15, 16, 17, 18))
                ),
            )
        )

        async def request_results() -> None:
            transport = httpx.ASGITransport(app=create_app(container))
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://127.0.0.1:8182",
                cookies={"incoooming_source": "schwab"},
            ) as client:
                for period in ("all", "1m", "3m", "6m", "1y"):
                    response = await client.get(f"/workspaces/attribution?period={period}")
                    assert response.status_code == 200
                    match = re.search(
                        r'<script type="application/json" data-performance-comparison-payload>'
                        r"(.*?)</script>",
                        response.text,
                        re.S,
                    )
                    assert match is not None
                    comparison = json.loads(match.group(1))
                    assert comparison["coverage_end"] == "2026-09-20"
                    assert comparison["actual"]["points"][-1]["valuation_phase"] == "off_session"
                    assert comparison["actual"]["points"][-1]["daily_return_percent"] is None
                    assert comparison["matched"]["as_of"] == "2026-09-18"
                    assert comparison["market_reference"]["points"][-1]["date"] == "2026-09-18"
                    assert "data-performance-freshness" in response.text
                    assert "Market closed" in response.text
                    assert "SEP 20, 2026" in response.text and "SEP 18, 2026" in response.text
                    assert 'data-performance-demo="false"' in response.text
                    assert "performance-compare.js?v=23" in response.text
                    assert "&middot; compared through SEP 18" in response.text

        asyncio.run(request_results())
    finally:
        container.close()
