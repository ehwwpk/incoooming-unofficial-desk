from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from schwab_dashboard.application.imports import parse_csv_file
from schwab_dashboard.application.market_time import ledger_market_date
from schwab_dashboard.domain.data_source import BrokerKind, ImportRecordKind

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "csv"


@pytest.mark.parametrize(
    ("broker", "relative", "profile", "imported"),
    (
        (BrokerKind.SCHWAB, "schwab/activity-with-preamble.csv", "schwab-web", 3),
        (BrokerKind.FIDELITY, "fidelity/positions.csv", "fidelity-web", 2),
        (
            BrokerKind.ROBINHOOD,
            "robinhood/activity.csv",
            "robinhood-account-activity",
            3,
        ),
        (BrokerKind.WEBULL, "webull/orders.csv", "webull-order-history", 1),
        (BrokerKind.IBKR, "ibkr/statement.csv", "ibkr-activity-statement", 4),
    ),
)
def test_broker_golden_files_normalize_safely(
    broker: BrokerKind, relative: str, profile: str, imported: int
) -> None:
    path = FIXTURES / relative
    parsed = parse_csv_file(filename=path.name, content=path.read_bytes(), broker=broker)

    assert parsed.profile == profile
    assert parsed.detected_broker is broker
    assert parsed.imported_count == imported
    assert parsed.confidence == "high"
    assert all(record.fingerprint and record.source_row_number for record in parsed.records)


def test_schwab_deposit_is_transfer_not_income_and_preamble_is_audited() -> None:
    path = FIXTURES / "schwab" / "activity-with-preamble.csv"
    parsed = parse_csv_file(filename=path.name, content=path.read_bytes(), broker=BrokerKind.SCHWAB)

    cash = [
        record.normalized
        for record in parsed.records
        if record.kind is ImportRecordKind.CASH_MOVEMENT
    ]
    assert {record["movement_type"] for record in cash} == {"dividend", "transfer"}
    assert (
        next(record for record in cash if record["movement_type"] == "transfer")["amount"]
        == "25000.00"
    )
    assert parsed.header_row == 4
    assert parsed.ignored_count >= 3
    assert parsed.capabilities == ("cash_movements", "dividends", "executions")
    assert "positions" not in parsed.capabilities


def test_fidelity_compact_option_symbol_is_normalized() -> None:
    path = FIXTURES / "fidelity" / "positions.csv"
    parsed = parse_csv_file(
        filename=path.name, content=path.read_bytes(), broker=BrokerKind.FIDELITY
    )

    option = next(
        record.normalized
        for record in parsed.records
        if record.normalized["asset_type"] == "OPTION"
    )
    assert option["underlying_symbol"] == "KTOS"
    assert option["expiration_date"] == "2026-08-21"
    assert option["strike"] == "75"
    assert option["contract_multiplier"] == "100"


def test_adjusted_option_uses_exported_multiplier_and_blocks_unknown_multiplier() -> None:
    path = FIXTURES / "generic" / "adjusted-options.csv"
    parsed = parse_csv_file(
        filename=path.name, content=path.read_bytes(), broker=BrokerKind.GENERIC
    )

    assert parsed.imported_count == 1
    assert parsed.review_count == 1
    imported = parsed.records[0].normalized
    assert imported["contract_multiplier"] == "150"
    assert imported["multiplier_source"] == "exported"
    assert imported["gross_amount"] == "150.00"


def test_numeric_occ_root_without_multiplier_is_treated_as_adjusted() -> None:
    content = (
        b"Account,Symbol,Description,Quantity,Last Price,Market Value\n"
        b"Brokerage 4321,CVX,Chevron Corp,100,195.00,19500.00\n"
        b"Brokerage 4321,XYZ1  260821C00050000,XYZ option,-1,1.00,-100.00\n"
    )

    parsed = parse_csv_file(filename="positions.csv", content=content)

    assert parsed.imported_count == 1
    assert parsed.review_count == 1
    assert "reliable exported multiplier" in next(
        row.reason or "" for row in parsed.rows if row.reason and "multiplier" in row.reason
    )


def test_adjusted_execution_uses_net_cash_to_recover_gross_credit() -> None:
    content = (
        b"Account,Date,Action,Symbol,Description,Quantity,Price,Fees,Amount\n"
        b"Brokerage 4321,08/01/2026,Sell to Open,XYZ1  260821C00050000,"
        b"XYZ option,1,1.00,1.00,149.00\n"
    )

    parsed = parse_csv_file(filename="activity.csv", content=content)
    execution = parsed.records[0].normalized

    assert execution["contract_multiplier"] is None
    assert execution["multiplier_source"] == "unknown_adjusted"
    assert execution["gross_amount"] == "150.00"
    assert execution["net_cash"] == "149.00"


def test_ambiguous_cash_is_preserved_without_becoming_owner_capital() -> None:
    content = (
        b"Account,Date,Action,Symbol,Description,Quantity,Price,Fees,Amount\n"
        b"Brokerage 4321,08/01/2026,Journal,,Internal adjustment,,,,$25000.00\n"
    )

    parsed = parse_csv_file(filename="activity.csv", content=content)

    assert parsed.records[0].kind is ImportRecordKind.CASH_MOVEMENT
    assert parsed.records[0].normalized["movement_type"] == "other"
    assert parsed.records[0].normalized["amount"] == "25000.00"


def test_ibkr_proceeds_are_made_fee_net_and_codes_preserve_position_effect() -> None:
    content = (
        b"Trades,Header,Asset Category,Symbol,Description,Date/Time,Quantity,T. Price,"
        b"Proceeds,Comm/Fee,Mult,Code\n"
        b"Trades,Data,Options,CVX  260821C00205000,CVX option,"
        b"2026-08-01 10:30:00,-1,1.25,125,-0.03,100,O\n"
    )

    parsed = parse_csv_file(filename="statement.csv", content=content, broker=BrokerKind.IBKR)
    execution = parsed.records[0].normalized

    assert execution["gross_amount"] == "125.00"
    assert execution["fees"] == "0.03"
    assert execution["net_cash"] == "124.97"
    assert execution["position_effect"] == "opening"
    assert ledger_market_date(
        datetime.fromisoformat(str(execution["occurred_at"]))
    ).isoformat() == ("2026-08-01")


def test_ibkr_bare_transfer_is_unresolved_cash_not_owner_capital() -> None:
    content = (
        b"Cash Transactions,Header,Currency,Date/Time,Description,Amount,Symbol\n"
        b"Cash Transactions,Data,USD,2026-08-02,Internal transfer,1000,\n"
    )

    parsed = parse_csv_file(filename="statement.csv", content=content, broker=BrokerKind.IBKR)

    assert parsed.records[0].normalized["movement_type"] == "other"


def test_ibkr_unsigned_withdrawal_is_normalized_to_an_owner_cash_outflow() -> None:
    content = (
        b"Cash Transactions,Header,Currency,Date/Time,Description,Amount,Symbol\n"
        b"Cash Transactions,Data,USD,2026-08-02,Withdrawal,250,\n"
    )

    parsed = parse_csv_file(filename="statement.csv", content=content, broker=BrokerKind.IBKR)

    assert parsed.records[0].normalized["movement_type"] == "transfer"
    assert parsed.records[0].normalized["amount"] == "-250"


def test_fingerprint_is_stable_when_a_broker_preamble_changes() -> None:
    path = FIXTURES / "schwab" / "activity-with-preamble.csv"
    original = path.read_bytes()
    changed = original.replace(b"Exported 08/12/2026", b"Exported 08/13/2026")

    first = parse_csv_file(filename=path.name, content=original, broker=BrokerKind.SCHWAB)
    second = parse_csv_file(filename=path.name, content=changed, broker=BrokerKind.SCHWAB)

    assert [record.fingerprint for record in first.records] == [
        record.fingerprint for record in second.records
    ]
