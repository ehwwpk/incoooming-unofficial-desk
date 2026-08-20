from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
from alembic import command

from schwab_dashboard.app import create_app
from schwab_dashboard.cli import _alembic_config
from schwab_dashboard.config import Settings
from schwab_dashboard.container import Container
from schwab_dashboard.domain.opportunity import RadarMode
from schwab_dashboard.infrastructure.demo.opportunity import DemoOpportunityMarketGateway


def test_demo_workspaces_have_independent_routes_and_honest_states(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path, demo_mode=True)
    command.upgrade(_alembic_config(settings), "head")
    container = Container(settings)

    try:
        catalog, desk, risk, review, radar, volatility, records = asyncio.run(
            _request_workspaces(container)
        )
        assert catalog.status_code == 200
        assert [item["key"] for item in catalog.json()] == [
            "desk",
            "risk",
            "attribution",
            "radar",
            "volatility",
            "records",
        ]
        assert len({item["window_name"] for item in catalog.json()}) == 6

        assert desk.status_code == 200
        nav_start = desk.text.index('class="product-nav"')
        nav = desk.text[nav_start : desk.text.index("</nav>", nav_start)]
        assert (
            nav.find("/workspaces/risk")
            < nav.find("/workspaces/radar")
            < nav.find("/workspaces/attribution")
        )
        assert "CHAIN RESEARCH" in nav
        assert "data-tools-toggle" not in desk.text
        assert "TOOLS" not in nav
        assert 'href="/workspaces/records"' in desk.text
        assert "desk-workspace-launcher" not in desk.text
        assert "function-rail" in desk.text
        assert "data-nibwick-stage" in desk.text
        assert "data-nibwick-lantern" in desk.text
        assert "data-nibwick-glare" in desk.text
        assert "nibwick-lantern-core" in desk.text
        assert "nibwick-lantern-glass" not in desk.text
        assert "data-nibwick-beam" not in desk.text
        nibwick_js = (
            Path(__file__)
            .resolve()
            .parents[2]
            .joinpath("src/schwab_dashboard/web/static/nibwick.js")
            .read_text(encoding="utf-8")
        )
        assert '["flare"' not in nibwick_js
        assert 'praying ? "PRAY"' in nibwick_js
        assert "atFloorHold(ms) && !compactRail.matches" in nibwick_js
        assert "sillFace" in nibwick_js
        assert "SILL_MS" in nibwick_js
        assert "BASE_CYCLE" in nibwick_js
        assert "SILL_START_MS" in nibwick_js
        assert "UP_SPAN" not in nibwick_js
        assert "SILL_UP_START" not in nibwick_js
        assert "SILL_PLANT" not in nibwick_js
        assert '["along", 1200]' not in nibwick_js
        assert '["away", 1400]' in nibwick_js
        assert '["camera", 1600]' in nibwick_js
        assert "PEER" not in nibwick_js
        assert (
            'status.textContent = praying ? "PRAY" : studying ? "STUDY" : clearing ? "CLEAR" : "PATROL"'
            in nibwick_js
        )
        assert "data-rail-link" not in desk.text
        assert "<kbd>F1</kbd>" not in desk.text
        assert "<kbd>F2</kbd>" not in desk.text
        assert "<kbd>F3</kbd>" not in desk.text
        assert "data-campaign-chart" in desk.text
        assert "/static/charts/campaign-chart.js" in desk.text
        assert "data-campaign-chart-fallback" in desk.text
        assert "data-campaign-chart-legacy" not in desk.text
        assert desk.text.count("data-campaign-chart data-symbol") == 3
        assert desk.text.count('class="position-move-tape"') == 3
        assert "Latest close versus the prior market-session close" in desk.text
        assert "Current price versus five market sessions earlier" in desk.text
        assert 'class="position-price-value"' in desk.text
        assert "CHECK FRESH CHAIN" in desk.text
        assert "NEAREST CASH AND TIME" in desk.text
        assert "source=cvx-0724-195" in desk.text
        assert "from=nibwick" in desk.text
        assert "returnAnchor=roll-option-cvx-0724-195" in desk.text
        assert "OPEN THIS CONTRACT" in desk.text

        assert risk.status_code == 200
        assert "Next expirations" in risk.text
        assert "CALENDAR CLOCK" in risk.text
        assert "STOCKS ·" in risk.text
        assert risk.text.count("data-open-book-section=") == 4
        assert "RISK LENS" in risk.text
        assert "Carry / IV" in risk.text
        assert "NET STOCK EXPOSURE" in risk.text
        assert "IV COST IN THETA DAYS" in risk.text
        assert "POSITION-ADJUSTED" in risk.text
        assert "DELTA &middot; NEXT $1" in risk.text
        assert "5D STOCK" in risk.text
        assert (
            "pressure is heating" in risk.text
            or "pressure is cooling" in risk.text
            or "roughly flat" in risk.text
        )
        assert "price-pressure-plain" in risk.text
        assert "IV +1" in risk.text
        assert "MODEL INPUTS" in risk.text
        assert 'data-open-book-section="calendar" open' in risk.text
        assert "CURRENT MODEL THETA / DAY" in risk.text
        assert "later expiries" in risk.text
        assert "EARNINGS DATE UNAVAILABLE" in risk.text
        assert "OPEN OWN WINDOW" in risk.text
        assert 'data-workspace-key="risk"' in risk.text
        assert "data-tools-toggle" not in risk.text
        assert ">TOOLS<" not in risk.text
        assert "workspace-tabs" not in risk.text
        assert "workspace-directory" not in risk.text
        assert 'class="workspace-breadcrumb"' in risk.text
        assert "BACK TO DESK" in risk.text
        assert "data-roll-board-contract=" in risk.text
        assert " · RV " in risk.text

        assert review.status_code == 200
        assert "Cash windows" in review.text
        assert "EXECUTED CASH" in review.text
        assert "Versus shares" in review.text
        assert "<h2>Campaigns</h2>" in review.text
        assert "Call campaigns" not in review.text
        campaigns_start = review.text.index('id="campaigns"')
        campaigns_html = review.text[campaigns_start : review.text.index("recorded-outcomes-title")]
        assert 'id="campaigns-open"' in campaigns_html
        assert 'id="campaigns-closed"' in campaigns_html
        assert "<b>OPEN</b>" in campaigns_html
        assert "<b>CLOSED</b>" in campaigns_html
        assert 'role="tablist"' not in campaigns_html
        assert "MONTH BY MONTH" in review.text
        assert "THROUGH AUG 07" in review.text
        assert "Cash cadence" in review.text
        assert review.text.count("data-results-cash-series") == 3
        assert 'data-results-cash-period="quarter"' in review.text
        assert 'data-results-cash-period="ytd"' in review.text
        assert 'data-results-cash-period="r365"' in review.text
        assert "/static/performance-compare.js" in review.text
        assert "DAILY CASH" not in review.text

        assert radar.status_code == 200
        assert "ON-DEMAND LOOKUP" in radar.text
        assert "SEPARATE FROM ACCOUNT SYNC" in radar.text
        assert "COVERED CALL" in radar.text
        assert "CASH-SECURED PUT" in radar.text
        assert "EXPIRATION MAP" in radar.text
        assert "Price / time" in radar.text
        assert "EXPAND MAP" in radar.text
        assert "PREMIUM / TIME" in radar.text
        assert "Selected contract market detail" in radar.text
        assert "NO FUTURE PRICE FORECAST" in radar.text
        assert "RSI 14" in radar.text
        assert "MACD 12/26/9" in radar.text
        assert "premium-radar-indicators.js" in radar.text
        assert "premium-radar-map.js" in radar.text
        assert "data-radar-roll-handoff" in radar.text
        assert "ROLL AN OPEN OPTION" in radar.text
        assert "data-radar-roll-source-picker" in radar.text
        assert "data-radar-roll-return" in radar.text
        assert 'data-symbol="CVX" data-mode="covered_call"' in radar.text
        assert 'value="CVX" data-radar-symbol' in radar.text
        assert 'data-radar-symbol-chip="CVX"' in radar.text
        assert 'data-radar-symbol-chip="KTOS"' in radar.text
        assert 'data-radar-symbol-chip="URNM"' in radar.text
        assert "Names you hold" in radar.text
        assert "Enter one ticker" not in radar.text
        assert "Visiting Radar does not fetch a chain" in radar.text
        assert "RV " in radar.text
        assert "RNG " in radar.text
        assert "data-tools-toggle" not in radar.text
        assert ">TOOLS<" not in radar.text

        assert volatility.status_code == 303
        assert volatility.headers["location"].endswith("/workspaces/radar")
        assert "Historical IV is not yet collected" not in volatility.text

        assert records.status_code == 200
        assert "<h2>Shares and options</h2>" in records.text
        assert "Shares and short calls" not in records.text
        assert 'href="/sources">BOOK</a>' in records.text
        assert ">TOOLS<" not in records.text
        assert "<h2>Adapters</h2>" in records.text
        assert "Multi-broker aggregator" in records.text
        assert "CONDITIONAL" in records.text
        assert "Cash events" in records.text
        assert "EXACT POSTING DATES" in records.text
        assert "Inactive calendar dates are intentionally omitted" in records.text
        assert "<h2>Option activity</h2>" in records.text
        assert "Covered-call activity" not in records.text
        assert "STRIKES TESTED 15\u201340% OTM" in records.text
    finally:
        container.close()


def test_demo_radar_roll_handoff_reprices_a_verified_open_call(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path, demo_mode=True)
    command.upgrade(_alembic_config(settings), "head")
    container = Container(settings)

    try:
        snapshot = container.read_dashboard("demo").execute()
        underlying = next(item for item in snapshot.underlyings if item.symbol == "KTOS")
        source = underlying.open_call_clocks[0]
        bundle = DemoOpportunityMarketGateway().fetch(
            symbol=underlying.symbol,
            mode=RadarMode.COVERED_CALL,
            from_date=snapshot.as_of.date(),
            to_date=snapshot.as_of.date(),
        )
        target = next(
            contract
            for contract in bundle.contracts
            if contract.option_side is RadarMode.COVERED_CALL.option_side
            and contract.expiration_date > source.expires_on
            and contract.strike > source.strike
        )
        response = asyncio.run(
            _post_radar_roll(
                container,
                symbol=underlying.symbol,
                source=source.record_id,
                target_expiration=str(target.expiration_date),
                target_strike=str(target.strike),
            )
        )

        assert response.status_code == 200
        payload = response.json()
        review = payload["roll_review"]
        assert payload["verdict"] == "ROLL REVIEW"
        assert len(payload["candidates"]) <= 10
        assert all(
            Decimal(candidate["strike"]) > source.strike
            and date.fromisoformat(candidate["expiration_date"]) > source.expires_on
            for candidate in payload["candidates"]
        )
        assert all(candidate["label"] is not None for candidate in payload["candidates"])
        assert review["source_option_symbol"] == source.record_id
        assert review["target_expiration_date"] == str(target.expiration_date)
        assert review["target_strike"] == str(target.strike)
        assert review["status"] == "matched"
        assert review["source_quote_status"] in {"desk_snapshot", "fresh_chain"}
        assert len(review["comparisons"]) == len(payload["candidates"])
        candidates_by_symbol = {
            candidate["option_symbol"]: candidate for candidate in payload["candidates"]
        }
        for comparison in review["comparisons"]:
            candidate = candidates_by_symbol[comparison["option_symbol"]]
            expected_net = Decimal(candidate["bid"]) - Decimal(review["source_close_ask_per_share"])
            assert Decimal(comparison["net_roll_per_share"]) == expected_net
            assert Decimal(comparison["net_roll_cash"]) == expected_net * Decimal(
                source.contracts * 100
            )
        target_comparison = next(
            comparison
            for comparison in review["comparisons"]
            if comparison["option_symbol"] == target.option_symbol
        )
        assert target_comparison["bid_per_share"] == str(target.bid)
        assert target_comparison["net_roll_per_share"] == review["net_roll_per_share"]
        assert target_comparison["net_roll_cash"] == review["net_roll_cash"]
        assert target_comparison["strike_change_per_share"] == str(target.strike - source.strike)
        assert target_comparison["added_days"] == (target.expiration_date - source.expires_on).days
        assert any(
            candidate["strike"] == str(target.strike)
            and candidate["expiration_date"] == str(target.expiration_date)
            for candidate in payload["candidates"]
        )

        refreshed_source = replace(
            target,
            option_symbol=source.record_id,
            expiration_date=source.expires_on,
            strike=source.strike,
            ask=Decimal("1.23"),
        )
        container.premium_radar()._market = _StaticOpportunityMarket(
            replace(bundle, contracts=(refreshed_source, *bundle.contracts))
        )
        refreshed = asyncio.run(
            _post_radar_roll(
                container,
                symbol=underlying.symbol,
                source=source.record_id,
                target_expiration=str(target.expiration_date),
                target_strike=str(target.strike),
            )
        )
        assert refreshed.status_code == 200
        refreshed_review = refreshed.json()["roll_review"]
        assert refreshed_review["source_quote_status"] == "fresh_chain"
        assert refreshed_review["source_close_ask_per_share"] == "1.23"

        stale = asyncio.run(
            _post_radar_roll(
                container,
                symbol=underlying.symbol,
                source="not-an-open-call",
                target_expiration=str(target.expiration_date),
                target_strike=str(target.strike),
            )
        )
        assert stale.status_code == 422
        assert "no longer open" in stale.json()["detail"]["message"]
    finally:
        container.close()


def test_demo_radar_can_start_a_roll_review_from_only_an_open_source(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path, demo_mode=True)
    command.upgrade(_alembic_config(settings), "head")
    container = Container(settings)

    try:
        snapshot = container.read_dashboard("demo").execute()
        underlying = next(item for item in snapshot.underlyings if item.symbol == "KTOS")
        source = underlying.open_call_clocks[0]
        response = asyncio.run(
            _post_radar_roll(
                container,
                symbol=underlying.symbol,
                source=source.record_id,
            )
        )

        assert response.status_code == 200
        payload = response.json()
        review = payload["roll_review"]
        assert payload["verdict"] == "ROLL REVIEW"
        assert review["source_option_symbol"] == source.record_id
        assert review["status"] in {"matched", "no_candidates"}
        assert len(review["comparisons"]) == len(payload["candidates"])
        if payload["candidates"]:
            first = payload["candidates"][0]
            assert review["status"] == "matched"
            assert review["target_expiration_date"] == first["expiration_date"]
            assert review["target_strike"] == first["strike"]
    finally:
        container.close()


def test_radar_policy_endpoint_accepts_a_leaps_window(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path, demo_mode=True)
    command.upgrade(_alembic_config(settings), "head")
    container = Container(settings)

    async def save_policy() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app(container))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            cookies={"incoooming_source": "demo"},
        ) as client:
            return await client.put(
                "/api/v1/radar/policies/SPY",
                json={
                    "mode": "covered_call",
                    "minimum_dte": 0,
                    "maximum_dte": 1095,
                    "minimum_annualized_rate_percent": "0",
                },
            )

    try:
        response = asyncio.run(save_policy())
        assert response.status_code == 200
        assert response.json()["minimum_dte"] == 0
        assert response.json()["maximum_dte"] == 1095
        assert Decimal(response.json()["minimum_annualized_rate_percent"]) == Decimal("0")
        assert response.json()["maximum_spread_percent"] is None
        assert response.json()["maximum_five_day_move_percent"] is None
    finally:
        container.close()


class _StaticOpportunityMarket:
    def __init__(self, bundle: object) -> None:
        self._bundle = bundle

    def fetch(self, **_: object) -> object:
        return self._bundle


def test_empty_live_ledger_keeps_workspaces_available_before_broker_auth(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)
    command.upgrade(_alembic_config(settings), "head")
    container = Container(settings)

    try:
        risk, results, volatility, records = asyncio.run(_request_pre_auth_workspaces(container))
        assert risk.status_code == 200
        assert "No normalized open short options are available" in risk.text
        assert 'data-workspace-key="risk"' in risk.text
        assert results.status_code == 200
        assert "No performance ledger is available yet" in results.text
        assert "Unsupported results remain blank" in results.text
        assert volatility.status_code == 303
        assert volatility.headers["location"].endswith("/workspaces/radar")
        assert "DEMO SOURCE" not in volatility.text
        assert records.status_code == 200
        assert "<h2>Option activity</h2>" in records.text
        assert "No short-option openings normalized." in records.text
        assert "STRIKES TESTED 15\u201340% OTM" not in records.text
        assert "Covered-call activity" not in records.text
    finally:
        container.close()


async def _request_workspaces(
    container: Container,
) -> tuple[
    httpx.Response,
    httpx.Response,
    httpx.Response,
    httpx.Response,
    httpx.Response,
    httpx.Response,
    httpx.Response,
]:
    transport = httpx.ASGITransport(app=create_app(container))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={"incoooming_source": "demo"},
    ) as client:
        responses = await asyncio.gather(
            client.get("/api/v1/workspaces"),
            client.get("/"),
            client.get("/workspaces/risk"),
            client.get("/workspaces/attribution"),
            client.get(
                "/workspaces/radar?symbol=CVX&mode=covered_call&review=roll"
                "&source=cvx-0724-195&targetExpiration=2026-09-03&targetStrike=215"
            ),
            client.get("/workspaces/volatility"),
            client.get("/workspaces/records"),
        )
    return tuple(responses)  # type: ignore[return-value]


async def _post_radar_roll(
    container: Container,
    *,
    symbol: str,
    source: str,
    target_expiration: str | None = None,
    target_strike: str | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=create_app(container))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={"incoooming_source": "demo"},
    ) as client:
        roll = {"source_option_symbol": source}
        if target_expiration is not None and target_strike is not None:
            roll.update(
                target_expiration=target_expiration,
                target_strike=target_strike,
            )
        return await client.post(
            "/api/v1/radar/lookups",
            json={
                "symbol": symbol,
                "mode": "covered_call",
                "roll": roll,
            },
        )


async def _request_pre_auth_workspaces(
    container: Container,
) -> tuple[httpx.Response, httpx.Response, httpx.Response, httpx.Response]:
    transport = httpx.ASGITransport(app=create_app(container))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={"incoooming_source": "schwab"},
    ) as client:
        risk, results, volatility, records = await asyncio.gather(
            client.get("/workspaces/risk"),
            client.get("/workspaces/attribution"),
            client.get("/workspaces/volatility"),
            client.get("/workspaces/records"),
        )
    return risk, results, volatility, records
