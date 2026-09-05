from __future__ import annotations

import asyncio
import json
import re
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from alembic import command

from schwab_dashboard.app import create_app
from schwab_dashboard.cli import _alembic_config
from schwab_dashboard.config import Settings
from schwab_dashboard.container import Container


def test_demo_results_periods_render_matched_history_and_honest_labels(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path, demo_mode=True)
    command.upgrade(_alembic_config(settings), "head")
    container = Container(settings)

    async def check() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(container)),
            base_url="http://127.0.0.1:8182",
            # A stale live-source cookie must not relabel a dedicated demo server.
            cookies={"incoooming_source": "schwab"},
        ) as client:
            desk = await client.get("/")
            assert "Current book: Demo book." in desk.text
            assert "Current book: Schwab live." not in desk.text
            dashboard = (await client.get("/api/v1/dashboard")).json()
            full_history = dashboard["performance_comparison"]["actual"]["points"]
            portfolio = dashboard["portfolio"]
            assert Decimal(full_history[-1]["value"]) == Decimal(portfolio["total_value"])
            assert Decimal(full_history[-1]["daily_return_percent"]) == Decimal(
                portfolio["day_profit_loss_percent"]
            )
            assert dashboard["option_outcomes"]["open_put_contracts"] == 2
            for period in ("1m", "3m", "6m", "1y", "all"):
                response = await client.get(f"/workspaces/attribution?period={period}")
                assert response.status_code == 200
                assert f'period={period}" aria-current="page"' in response.text
                assert 'data-performance-demo="true"' in response.text
                assert "SIMULATED RETURNS" in response.text
                assert "FEE-NET BROKER CASH" not in response.text
                assert "DAILY RISK USES ADJACENT BROKER-OBSERVED CLOSES ONLY" not in response.text
                match = re.search(
                    r"data-performance-comparison-payload>(.*?)</script>", response.text, re.S
                )
                assert match is not None
                payload = json.loads(match.group(1))
                assert payload["matched"]["status"] == "matched"
                dates = {
                    payload[key]["points"][-1]["date"]
                    for key in (
                        "actual",
                        "shares_without_options",
                        "market_reference",
                        "levered_market_reference",
                    )
                }
                assert dates == {"2026-08-07"}
                if period == "1m":
                    assert len(payload["actual"]["points"]) < len(full_history)

    try:
        asyncio.run(check())
    finally:
        container.close()


@pytest.mark.parametrize(
    ("demo_mode", "source"), [(False, "demo"), (False, "csv:test"), (True, "schwab")]
)
def test_nonlive_source_blocks_stale_live_sync_actions(
    tmp_path: Path, demo_mode: bool, source: str
) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path, demo_mode=demo_mode)
    command.upgrade(_alembic_config(settings), "head")
    container = Container(settings)
    sync = Mock(side_effect=AssertionError("A nonlive book must not invoke a broker sync"))
    container.sync_full = sync
    container.sync_accounts = sync

    async def check() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(container)),
            base_url="http://127.0.0.1:8182",
            cookies={"incoooming_source": source},
        ) as client:
            for route in ("/sync", "/api/v1/sync/full", "/api/v1/sync/accounts"):
                response = await client.post(route)
                assert response.status_code == 409
                assert "Switch to the Schwab book" in response.text
        sync.assert_not_called()

    try:
        asyncio.run(check())
    finally:
        container.close()
