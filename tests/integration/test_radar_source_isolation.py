from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest
from alembic import command
from fastapi.testclient import TestClient

from schwab_dashboard.app import create_app
from schwab_dashboard.application.rolls.board import build_roll_board
from schwab_dashboard.application.services.run_premium_radar import RadarRollRequest
from schwab_dashboard.cli import _alembic_config
from schwab_dashboard.config import Settings
from schwab_dashboard.container import Container
from schwab_dashboard.domain.instruments import OptionSide
from schwab_dashboard.domain.opportunity import RadarMode, RadarPolicy
from schwab_dashboard.infrastructure.demo.fixtures.holdings import HOLDINGS
from schwab_dashboard.infrastructure.secrets.keyring_tokens import KeyringTokenStore


def test_selecting_demo_isolates_every_radar_route_from_live_data(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None, data_dir=tmp_path, schwab_app_key=None, schwab_app_secret=None
    )
    command.upgrade(_alembic_config(settings), "head")
    container = Container(settings)
    live_market = Mock()
    live_market.fetch.side_effect = AssertionError("Demo attempted a live market lookup")
    container.premium_radar("schwab")._market = live_market
    live = container.opportunity_store
    live.save_policy(
        RadarPolicy(
            symbol="CVX", mode=RadarMode.COVERED_CALL, minimum_annualized_rate_percent=Decimal("77")
        )
    )
    live.save_symbol(symbol="SPY", source="schwab", saved_at=datetime.now(UTC))
    live_lookup_id = live.create_lookup(
        symbol="SPY",
        mode=RadarMode.COVERED_CALL,
        source="schwab",
        requested_at=datetime.now(UTC),
    )
    try:
        with TestClient(create_app(container), base_url="http://127.0.0.1:8182") as client:
            client.post("/sources/select", data={"source_key": "demo"}, follow_redirects=False)
            policy = client.get("/api/v1/radar/policies/CVX", params={"mode": "covered_call"})
            assert policy.status_code == 200
            assert Decimal(policy.json()["minimum_annualized_rate_percent"]) == Decimal("5")
            saved_policy = client.put(
                "/api/v1/radar/policies/CVX",
                json={"mode": "covered_call", "minimum_annualized_rate_percent": "9"},
            )
            assert saved_policy.status_code == 200
            assert saved_policy.json()["version"] == 1
            assert (
                client.post("/api/v1/radar/saved-symbols", json={"symbol": "CVX"}).status_code
                == 204
            )
            symbols = client.get("/api/v1/radar/symbols").json()
            assert symbols["saved"] == ["CVX"]
            assert set(symbols["book"]) == {holding.symbol for holding in HOLDINGS}
            assert client.get(f"/api/v1/radar/lookups/{live_lookup_id}").status_code == 404

            lookup = client.post(
                "/api/v1/radar/lookups", json={"symbol": "CVX", "mode": "covered_call"}
            )
            assert lookup.status_code == 200
            payload = lookup.json()
            demo_lookup_id = payload["lookup_id"]
            assert payload["source"] == "demo"
            assert payload["observed_at"].startswith("2026-08-07")
            assert Decimal(payload["underlying_price"]) == HOLDINGS[0].current_price
            stored = client.get(f"/api/v1/radar/lookups/{demo_lookup_id}")
            assert stored.status_code == 200
            assert stored.json()["source"] == "demo"
            assert client.delete("/api/v1/radar/saved-symbols/CVX").status_code == 204
            assert client.get("/api/v1/radar/symbols").json()["saved"] == []

            client.post("/sources/select", data={"source_key": "schwab"}, follow_redirects=False)
            assert client.get(f"/api/v1/radar/lookups/{demo_lookup_id}").status_code == 404
            original_policy = client.get(
                "/api/v1/radar/policies/CVX", params={"mode": "covered_call"}
            ).json()
            assert Decimal(original_policy["minimum_annualized_rate_percent"]) == Decimal("77")
        assert live.list_saved_symbols(source="schwab") == ("SPY",)
        assert live.load_lookup(demo_lookup_id) is None
        live_market.fetch.assert_not_called()
    finally:
        container.close()


def test_demo_server_does_not_open_credential_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    load_token = Mock(side_effect=AssertionError("Demo opened the credential store"))
    monkeypatch.setattr(KeyringTokenStore, "load", load_token)
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        demo_mode=True,
        schwab_app_key="fictional-demo-key",
        schwab_app_secret="fictional-demo-secret",
    )
    container = Container(settings)
    try:
        assert container.oauth is None
        assert not container.token_available()
        assert container.premium_radar("schwab") is container.premium_radar("demo")
        result = container.premium_radar().execute(symbol="CVX", mode=RadarMode.COVERED_CALL)
        assert result.source == "demo"
        assert result.observed_at == container.read_dashboard("demo").execute().as_of
        load_token.assert_not_called()
    finally:
        container.close()


def test_demo_roll_board_and_radar_use_the_same_frozen_contract_quotes(tmp_path: Path) -> None:
    container = Container(Settings(_env_file=None, data_dir=tmp_path, demo_mode=True))
    try:
        snapshot = container.read_dashboard("demo").execute()
        radar = container.premium_radar("demo")
        board = build_roll_board(snapshot)
        checked_sides: set[OptionSide] = set()
        for row in board.rows:
            mode = (
                RadarMode.COVERED_CALL
                if row.source.option_side is OptionSide.CALL
                else RadarMode.CASH_SECURED_PUT
            )
            radar.save_policy(
                RadarPolicy(
                    symbol=row.symbol,
                    mode=mode,
                    maximum_dte=120,
                    minimum_annualized_rate_percent=Decimal("0"),
                )
            )
            for candidate in row.candidates:
                result = radar.execute(
                    symbol=row.symbol,
                    mode=mode,
                    snapshot=snapshot,
                    roll_request=RadarRollRequest(
                        source_option_symbol=row.source.option_symbol,
                        target_expiration=candidate.expires_on,
                        target_strike=candidate.strike,
                    ),
                )
                review = result.roll_review
                assert review is not None
                assert review.target_expiration_date == candidate.expires_on
                assert review.target_strike == candidate.strike
                assert review.source_close_ask_per_share == row.source.close_ask_per_share
                assert review.target_bid_per_share == candidate.sell_bid_per_share
                assert review.net_roll_cash == candidate.net_roll_cash
                assert result.observed_at == snapshot.as_of
                checked_sides.add(row.source.option_side)
        assert checked_sides == {OptionSide.CALL, OptionSide.PUT}
    finally:
        container.close()


def test_demo_radar_five_session_returns_match_the_desk_tape(tmp_path: Path) -> None:
    container = Container(Settings(_env_file=None, data_dir=tmp_path, demo_mode=True))
    try:
        snapshot = container.read_dashboard("demo").execute()
        radar = container.premium_radar("demo")
        for underlying in snapshot.underlyings:
            result = radar.execute(
                symbol=underlying.symbol, mode=RadarMode.COVERED_CALL, snapshot=snapshot
            )
            start = underlying.price_points[-6].price
            expected = (underlying.price_points[-1].price - start) / start * 100
            assert result.five_day_move_percent == expected
            assert result.underlying_price == underlying.current_price
    finally:
        container.close()
