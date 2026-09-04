from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

import httpx
from alembic import command
from sqlalchemy import inspect

from schwab_dashboard.app import create_app
from schwab_dashboard.cli import _alembic_config
from schwab_dashboard.config import Settings
from schwab_dashboard.container import Container
from schwab_dashboard.domain.data_source import BrokerKind

POSITIONS = (
    b"Account,Symbol,Description,Quantity,Last Price,Market Value,Average Price,"
    b"Day Change P&L,Open Profit Loss\n"
    b"Brokerage 4321,CVX,Chevron Corp,100,195.00,19500.00,150.00,125.00,4500.00\n"
    b"Brokerage 4321,CVX  260821C00205000,CVX 08/21/2026 205 Call,-1,1.25,"
    b"-125.00,2.00,5.00,75.00\n"
)

ACTIVITY = (
    b"Account,Date,Action,Symbol,Description,Quantity,Price,Fees,Amount\n"
    b"Brokerage 4321,08/01/2026,Sell to Open,CVX  260821C00205000,"
    b"CVX 08/21/2026 205 Call,1,1.25,0.03,124.97\n"
    b"Brokerage 4321,08/02/2026,Dividend,CVX,Chevron dividend,,,,171.00\n"
)

EXAMPLE_CSV_DIR = Path(__file__).resolve().parents[2] / "examples" / "csv"


def test_source_dataset_migration_round_trips(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)
    config = _alembic_config(settings)
    command.upgrade(config, "head")
    container = Container(settings)
    try:
        assert "source_datasets" in inspect(container.engine).get_table_names()
    finally:
        container.close()

    command.downgrade(config, "20260811_0010")
    downgraded = Container(settings)
    try:
        assert "source_datasets" not in inspect(downgraded.engine).get_table_names()
    finally:
        downgraded.close()

    command.upgrade(config, "head")
    upgraded = Container(settings)
    try:
        assert "source_datasets" in inspect(upgraded.engine).get_table_names()
    finally:
        upgraded.close()


def test_first_visit_chooses_a_source_and_csv_book_remains_isolated(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)
    command.upgrade(_alembic_config(settings), "head")
    container = Container(settings)
    try:
        responses = asyncio.run(_exercise_gateway(container))
        first, gateway, imported, dashboard, live_switch = responses

        assert first.status_code == 303
        assert first.headers["location"] == "/sources"
        assert gateway.status_code == 200
        assert "Get Incoooming" in gateway.text
        assert "DATA HEALTH" in gateway.text
        assert 'href="/workspaces/records"' in gateway.text
        assert gateway.text.count("/static/incoooming-operators.png") == 2
        assert "brand-nibwick-mark" not in gateway.text
        assert gateway.text.count("/static/nibwick-favicon.svg") >= 1
        assert "gateway-option-chart" in gateway.text
        assert "gateway-market-slab" in gateway.text
        assert "NVDA" in gateway.text
        assert "JUL 01&ndash;AUG 12" in gateway.text
        assert "$220C" in gateway.text
        assert "$230C" in gateway.text
        assert "$240C" in gateway.text
        assert "gateway-event-mini" in gateway.text
        assert gateway.text.count("gateway-event-hit event-") == 6
        assert "HOVER OR FOCUS A SQUARE FOR DETAILS" in gateway.text
        assert "gateway-daily-points" in gateway.text
        assert "gateway-chart-now" in gateway.text
        assert gateway.text.count("gateway-chart-event event-") == 6
        assert "gateway-cycle-link cycle-expired" in gateway.text
        assert "gateway-cycle-link cycle-rolled" in gateway.text
        assert "gateway-cycle-link cycle-closed" in gateway.text
        assert "gateway-paper-fountain" not in gateway.text
        assert "gateway-portal" not in gateway.text
        assert "INSIDE BOOK" not in gateway.text
        assert "<b>BOOK</b>" not in gateway.text
        assert 'name="theme-color" content="#0b0c0e"' in gateway.text
        assert "Live Schwab through your approved Developer API. Broker CSV. Demo." in gateway.text
        assert "CHOOSE SOURCE" not in gateway.text
        assert "This is not a normal Schwab customer login" in gateway.text
        assert "Connect your approved Schwab app." in gateway.text
        assert "Wake the live book." not in gateway.text
        assert "Bring your own ledger." in gateway.text
        assert "Explore a fictional portfolio." in gateway.text
        assert 'type="radio" name="broker" value="robinhood"' in gateway.text
        assert gateway.text.count("/static/nibwick-favicon.svg") >= 1
        favicon = (
            Path(__file__)
            .resolve()
            .parents[2]
            .joinpath("src/schwab_dashboard/web/static/nibwick-favicon.svg")
            .read_text(encoding="utf-8")
        )
        assert 'text-anchor="middle"' not in favicon
        assert "Cascadia Code" in favicon
        assert "#f0bd4f" in favicon
        assert "()___()" in favicon
        assert "( o   o )" in favicon
        assert "`-._.-'" in favicon
        assert "/   \\" not in favicon
        assert "/static/sources-art.css" in gateway.text
        assert "/static/nibwick-promenade.css" not in gateway.text
        assert "gateway-promenade" not in gateway.text
        assert "data-source-route=" not in gateway.text
        assert "()___()" not in gateway.text
        assert "FORMAT CHECKED." in gateway.text
        assert "Preview stops mismatches and uncertain rows" in gateway.text
        assert imported.status_code == 303
        assert imported.headers["location"] == "/"
        assert "incoooming_source=csv:" in imported.headers["set-cookie"]
        assert dashboard.status_code == 200
        assert 'data-demo-mode="false"' in dashboard.text
        assert "CSV BOOK" in dashboard.text
        assert "CVX" in dashboard.text
        assert "AUGUST IMPORT" in dashboard.text
        assert ">BOOK</a>" in dashboard.text
        assert "RECONNECT SCHWAB" not in dashboard.text
        assert live_switch.status_code == 303
        assert "incoooming_source=schwab" in live_switch.headers["set-cookie"]

        datasets = container.source_store.list_datasets()
        assert len(datasets) == 1
        assert datasets[0].broker is BrokerKind.GENERIC
        assert datasets[0].position_count == 2
        assert datasets[0].activity_count == 2
        assert container.read_dashboard(f"csv:{datasets[0].id}").execute().mode == "csv"
        assert container.read_dashboard("schwab").execute().positions == ()
        assert container.read_dashboard("schwab").execute().call_history == ()
    finally:
        container.close()


def test_realistic_csv_book_projects_inventory_options_income_and_dividend(
    tmp_path: Path,
) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)
    command.upgrade(_alembic_config(settings), "head")
    container = Container(settings)
    try:
        dataset = container.import_csv_dataset().execute(
            name="Three-name mock book",
            broker=BrokerKind.GENERIC,
            files=(
                ("mock-positions.csv", (EXAMPLE_CSV_DIR / "mock-positions.csv").read_bytes()),
                ("mock-activity.csv", (EXAMPLE_CSV_DIR / "mock-activity.csv").read_bytes()),
            ),
        )
        snapshot = container.read_dashboard(f"csv:{dataset.id}").execute()

        assert dataset.state.value == "ready"
        assert dataset.position_count == 6
        assert dataset.activity_count == 4
        assert snapshot.mode == "csv"
        assert snapshot.portfolio.total_value == Decimal("215606.00")
        assert snapshot.portfolio.gross_position_value == Decimal("217056.00")
        assert snapshot.portfolio.day_profit_loss is None
        assert snapshot.portfolio.day_profit_loss_source == "unavailable"
        assert snapshot.portfolio.open_position_day_profit_loss is not None
        assert snapshot.live_position_book is not None
        assert snapshot.live_position_book.total_shares == 2_000
        assert snapshot.live_position_book.open_call_contracts == 7
        assert snapshot.risk.daily_theta is None
        assert all(
            call.implied_volatility_percent is None
            and call.delta is None
            and call.gamma is None
            and call.theta_per_share is None
            and call.vega is None
            for call in snapshot.live_position_book.calls
        )
        assert {item.symbol for item in snapshot.underlyings} == {"CVX", "KTOS", "URNM"}
        assert all(item.average_open_call_iv_percent is None for item in snapshot.underlyings)
        assert all(item.average_open_call_delta is None for item in snapshot.underlyings)
        # Fixture activity is in August; use the quarter so this assertion does
        # not expire when the wall clock crosses into September.
        assert snapshot.income.quarter == Decimal("1049.79")
        assert snapshot.income.year_to_date == Decimal("2246.79")
        assert any(item.action_label == "DIVIDEND RECEIVED" for item in snapshot.cash_events)
        assert len(snapshot.campaigns) == 3
        assert {item.symbol for item in snapshot.campaigns} == {"CVX", "KTOS", "URNM"}
        assert all(item.status == "OPEN" for item in snapshot.campaigns)
        assert all(item.campaign_label.startswith("C") for item in snapshot.campaigns)
        assert len(snapshot.call_history) == 3
        assert {item.symbol for item in snapshot.call_history} == {"CVX", "KTOS", "URNM"}
        assert all(item.outcome == "Open" for item in snapshot.call_history)
        assert all(item.option_side == "CALL" for item in snapshot.call_history)
        assert all(item.sale_signal == "" for item in snapshot.call_history)
        assert [item.contracts for item in snapshot.call_history] == [2, 3, 2]

        dashboard, results, risk, api = asyncio.run(_render_csv_book(container, dataset.id))
        assert all(response.status_code == 200 for response in (dashboard, results, risk, api))
        assert "IMPORTED POS" in dashboard.text
        assert "$215,606.00" in dashboard.text
        assert "Portfolio value covers imported positions, not brokerage cash" in dashboard.text
        assert "imported position mark" in dashboard.text
        assert "latest Schwab mark" not in dashboard.text
        assert "Account returns and benchmark comparisons need dated balances" in results.text
        assert "Net option cash" in results.text
        assert "data-performance-comparison-payload" not in results.text
        assert "POSITION OPENING CREDIT" in risk.text
        assert "MODEL INPUTS" in risk.text
        assert "PER SHARE / UNAVAILABLE" in risk.text
        assert api.json()["mode"] == "csv"
        assert api.json()["portfolio"]["total_value"] == "215606.00"
    finally:
        container.close()


def test_csv_source_choice_runs_adapter_detection_and_preserves_safe_records(
    tmp_path: Path,
) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)
    command.upgrade(_alembic_config(settings), "head")
    container = Container(settings)
    try:
        datasets = tuple(
            container.import_csv_dataset().execute(
                name=f"{broker.value} source check",
                broker=broker,
                files=((f"{broker.value}-positions.csv", POSITIONS),),
            )
            for broker in BrokerKind
        )

        assert tuple(dataset.broker for dataset in datasets) == tuple(BrokerKind)
        assert all(dataset.position_count == 2 for dataset in datasets)
        assert all(dataset.capabilities for dataset in datasets)
        assert any(
            dataset.warnings for dataset in datasets if dataset.broker is not BrokerKind.GENERIC
        )
    finally:
        container.close()


async def _exercise_gateway(container: Container) -> tuple[httpx.Response, ...]:
    transport = httpx.ASGITransport(app=create_app(container))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8182",
        follow_redirects=False,
    ) as client:
        first = await client.get("/")
        gateway = await client.get("/sources")
        imported = await client.post(
            "/sources/csv",
            data={
                "dataset_name": "August import",
                "broker": "generic",
                "preview_fingerprint": container.import_csv_dataset()
                .preview(
                    name="August import",
                    broker=BrokerKind.GENERIC,
                    files=(("positions.csv", POSITIONS), ("activity.csv", ACTIVITY)),
                )
                .fingerprint,
            },
            files=[
                ("files", ("positions.csv", POSITIONS, "text/csv")),
                ("files", ("activity.csv", ACTIVITY, "text/csv")),
            ],
        )
        dashboard = await client.get("/")
        live_switch = await client.post(
            "/sources/select",
            data={"source_key": "schwab"},
        )
    return first, gateway, imported, dashboard, live_switch


async def _render_csv_book(
    container: Container,
    dataset_id: str,
) -> tuple[httpx.Response, ...]:
    transport = httpx.ASGITransport(app=create_app(container))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8182",
        follow_redirects=False,
        cookies={"incoooming_source": f"csv:{dataset_id}"},
    ) as client:
        return (
            await client.get("/"),
            await client.get("/workspaces/attribution"),
            await client.get("/workspaces/risk"),
            await client.get("/api/v1/dashboard"),
        )
