from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine, select, text

from schwab_dashboard.application.services.read_dashboard import ReadDashboard
from schwab_dashboard.application.services.record_ledger_activity import RecordLedgerActivity
from schwab_dashboard.application.services.run_premium_radar import _account_context
from schwab_dashboard.application.services.sync_accounts import SyncAccountsAndPositions
from schwab_dashboard.cli import _alembic_config
from schwab_dashboard.config import Settings
from schwab_dashboard.domain.instruments import AssetType
from schwab_dashboard.domain.ledger import LedgerActivityBatch
from schwab_dashboard.domain.opportunity import RadarMode, RadarPolicy
from schwab_dashboard.infrastructure.database.analytics_reader import SqlLiveAnalyticsReader
from schwab_dashboard.infrastructure.database.engine import create_session_factory
from schwab_dashboard.infrastructure.database.tables import (
    InstrumentTable,
    OptionLifecycleEventTable,
    PositionSnapshotTable,
    RawBrokerEventTable,
)
from schwab_dashboard.infrastructure.database.uow import build_uow_factory
from schwab_dashboard.infrastructure.database.uow_truth import build_truth_uow_factory
from schwab_dashboard.infrastructure.schwab.mapper import SchwabAccountMapper
from schwab_dashboard.infrastructure.schwab.transaction_mapper import SchwabTransactionMapper
from tests.fakes import FakeBrokerGateway

NOW = datetime(2026, 9, 10, 18, tzinfo=UTC)
ETF = {
    "assetType": "COLLECTIVE_INVESTMENT",
    "type": "EXCHANGE_TRADED_FUND",
    "symbol": "FUNDX",
    "cusip": "fixture-fund",
    "instrumentId": "fixture-id",
    "description": "Fictional exchange traded fund",
}
OPTION = {
    "assetType": "OPTION",
    "symbol": "FUNDX 301220C00055000",
    "instrumentId": "fixture-call",
    "underlyingSymbol": "FUNDX",
    "putCall": "CALL",
    "optionPremiumMultiplier": 100,
    "nonStandard": False,
}


@pytest.mark.parametrize(
    "subtype,expected",
    [
        ("EXCHANGE_TRADED_FUND", "ETF"),
        (" exchange_traded_fund ", "ETF"),
        ("UNIT_INVESTMENT_TRUST", "COLLECTIVE_INVESTMENT"),
        ("MUTUAL_FUND", "COLLECTIVE_INVESTMENT"),
        (None, "COLLECTIVE_INVESTMENT"),
    ],
)
def test_broker_subtype_controls_share_eligibility(subtype: str | None, expected: str) -> None:
    instrument = dict(ETF, type=subtype, description="ETF in a name is not proof")
    records = _accounts(instrument)
    assert records[0].positions[0].asset_type == expected
    trade = _trade(instrument)
    mapped = SchwabTransactionMapper().map(trade, observed_at=NOW)
    assert mapped.instruments[0].asset_type is (
        AssetType.ETF if expected == "ETF" else AssetType.MUTUAL_FUND
    )
    assert mapped.executions[0].quantity == Decimal("400")
    assert records[0].raw_payload["securitiesAccount"]["positions"][0]["instrument"] == instrument


def test_legacy_etf_repair_restores_book_radar_and_history_and_survives_resync(
    tmp_path: Path,
) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)
    config = _alembic_config(settings)
    command.upgrade(config, "20260903_0021")
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    uow_factory = build_uow_factory(sessions)
    truth_factory = build_truth_uow_factory(sessions)
    mapper = SchwabTransactionMapper()
    ledger = RecordLedgerActivity(uow_factory=truth_factory)
    accounts = _accounts(ETF)
    SyncAccountsAndPositions(
        broker=FakeBrokerGateway(list(accounts)),
        uow_factory=uow_factory,
        parser_version="fixture-v2",
    ).execute()
    payloads = [_trade(ETF), _delivery()]
    batches = []
    for payload in payloads:
        with uow_factory() as uow:
            run_id = uow.sync_runs.start(source="schwab_transactions", started_at=NOW)
            raw_id = uow.raw_events.add(
                sync_run_id=run_id,
                item_key=payload["activityId"],
                event_type="transaction",
                account_external_key="fixture-account",
                observed_at=NOW,
                parser_version="fixture-v2",
                payload=payload,
            )
            uow.sync_runs.complete(run_id, completed_at=NOW, account_count=1, position_count=0)
            uow.commit()
        mapped = mapper.map(payload, observed_at=NOW)
        batch = LedgerActivityBatch(
            source="schwab",
            account_external_key="fixture-account",
            raw_event_id=raw_id,
            instruments=mapped.instruments,
            executions=mapped.executions,
            lifecycle_events=mapped.lifecycle_events,
            cash_movements=mapped.cash_movements,
        )
        ledger.execute(batch)
        batches.append(batch)
    with sessions() as session:
        for row in session.scalars(select(PositionSnapshotTable)):
            if row.symbol == "FUNDX":
                row.asset_type = "COLLECTIVE_INVESTMENT"
        for row in session.scalars(select(InstrumentTable)):
            if row.symbol == "FUNDX":
                row.asset_type = "mutual_fund"
        for row in session.scalars(select(OptionLifecycleEventTable)):
            row.stock_instrument_id = row.stock_quantity = row.cash_amount = None
            row.details = dict(row.details, delivery_ambiguous=True)
        session.commit()
        raw_before = [
            (row.id, deepcopy(row.payload), row.payload_hash)
            for row in session.scalars(select(RawBrokerEventTable))
        ]
    analytics = SqlLiveAnalyticsReader(sessions)
    reader = ReadDashboard(
        uow_factory=uow_factory,
        analytics_reader=analytics,
        credentials_configured=False,
        token_available=False,
        clock=lambda: NOW,
    )
    before = reader.execute()
    assert before.live_position_book.underlyings[0].shares == 0
    command.upgrade(config, "head")
    snapshot = reader.execute()
    book = snapshot.live_position_book
    assert book is not None
    fund = next(item for item in book.underlyings if item.symbol == "FUNDX")
    assert (
        fund.shares,
        fund.contract_capacity,
        fund.covered_contracts,
        fund.uncovered_contracts,
    ) == (Decimal("400"), 4, 2, 0)
    assert book.total_shares == Decimal("400")
    context = _account_context(
        snapshot,
        symbol="FUNDX",
        policy=RadarPolicy(symbol="FUNDX", mode=RadarMode.COVERED_CALL, allowed_contracts=5),
    )
    assert context.shares == Decimal("400")
    assert context.available_call_lots == 2
    assert analytics.list_position_history()[0]["asset_type"] == "ETF"
    assert analytics.list_executions()[0]["asset_type"] == "etf"
    with sessions() as session:
        assert raw_before == [
            (row.id, row.payload, row.payload_hash)
            for row in session.scalars(select(RawBrokerEventTable))
        ]
        event = session.scalar(select(OptionLifecycleEventTable))
        assert event.stock_instrument_id is not None
        assert event.stock_quantity == Decimal("100")
        assert event.cash_amount == Decimal("5500")
        assert "delivery_ambiguous" not in event.details
    # An old activity fetched again must not conflict with the repaired record.
    for batch in batches:
        ledger.execute(batch)
    command.downgrade(config, "20260903_0021")
    command.upgrade(config, "head")
    assert reader.execute().live_position_book.total_shares == Decimal("400")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM executions")).scalar() == 1
        assert (
            connection.execute(text("SELECT COUNT(*) FROM option_lifecycle_events")).scalar() == 1
        )
    engine.dispose()


def _accounts(instrument: dict):
    return SchwabAccountMapper().map_records(
        [{"accountNumber": "fixture-number", "hashValue": "fixture-account"}],
        [
            {
                "securitiesAccount": {
                    "accountNumber": "fixture-number",
                    "type": "CASH",
                    "positions": [
                        {
                            "longQuantity": 400,
                            "shortQuantity": 0,
                            "averagePrice": 50,
                            "marketValue": 20000,
                            "instrument": instrument,
                        },
                        {
                            "longQuantity": 0,
                            "shortQuantity": 2,
                            "averagePrice": 1,
                            "marketValue": -100,
                            "instrument": OPTION,
                        },
                    ],
                }
            }
        ],
    )


@pytest.mark.parametrize("case", ["unknown", "trust", "mutual", "wrong_identity", "csv"])
def test_migration_does_not_promote_unproven_or_unrelated_funds(tmp_path: Path, case: str) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)
    config = _alembic_config(settings)
    command.upgrade(config, "20260903_0021")
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    instrument = dict(ETF)
    if case in {"unknown", "trust", "mutual"}:
        instrument["type"] = {
            "unknown": None,
            "trust": "UNIT_INVESTMENT_TRUST",
            "mutual": "MUTUAL_FUND",
        }[case]
    SyncAccountsAndPositions(
        broker=FakeBrokerGateway(list(_accounts(instrument))),
        uow_factory=build_uow_factory(sessions),
        parser_version="fixture-v2",
    ).execute()
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE position_snapshots SET asset_type='COLLECTIVE_INVESTMENT' "
                "WHERE symbol='FUNDX'"
            )
        )
        if case == "wrong_identity":
            connection.execute(
                text(
                    "UPDATE position_snapshots SET instrument_key='unrelated' WHERE symbol='FUNDX'"
                )
            )
        if case == "csv":
            connection.execute(text("UPDATE accounts SET source='csv:fixture'"))
    command.upgrade(config, "head")
    with sessions() as session:
        row = session.scalar(
            select(PositionSnapshotTable).where(PositionSnapshotTable.symbol == "FUNDX")
        )
        assert row.asset_type == "COLLECTIVE_INVESTMENT"
        assert row.long_quantity == Decimal("400")
    engine.dispose()


@pytest.mark.parametrize("extra_leg", ["option", "stock", "unknown_fund"])
def test_etf_deliveries_retain_ambiguity_when_share_or_option_leg_is_not_unique(
    extra_leg: str,
) -> None:
    payload = _delivery()
    if extra_leg == "unknown_fund":
        payload["transferItems"][1]["instrument"] = dict(ETF, type=None)
    else:
        instrument = (
            dict(OPTION, instrumentId="other-option")
            if extra_leg == "option"
            else {"assetType": "EQUITY", "symbol": "OTHER", "instrumentId": "other-stock"}
        )
        payload["transferItems"].append({"amount": 1, "instrument": instrument})
    mapped = SchwabTransactionMapper().map(payload, observed_at=NOW)
    assert all(event.stock_instrument_external_key is None for event in mapped.lifecycle_events)
    assert all(event.details["delivery_ambiguous"] is True for event in mapped.lifecycle_events)


def _trade(instrument: dict) -> dict:
    return {
        "activityId": "fixture-buy",
        "type": "TRADE",
        "time": NOW.isoformat(),
        "netAmount": -20000,
        "transferItems": [{"amount": 400, "cost": -20000, "price": 50, "instrument": instrument}],
    }


def _delivery() -> dict:
    return {
        "activityId": "fixture-assignment",
        "type": "RECEIVE_AND_DELIVER",
        "description": "Option assignment",
        "time": NOW.isoformat(),
        "netAmount": 5500,
        "transferItems": [
            {"amount": 1, "positionEffect": "CLOSING", "instrument": OPTION},
            {"amount": -100, "instrument": ETF},
        ],
    }
