from __future__ import annotations

from pathlib import Path

import pytest

from schwab_dashboard.application.imports import parse_csv_file
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


def test_fingerprint_is_stable_when_a_broker_preamble_changes() -> None:
    path = FIXTURES / "schwab" / "activity-with-preamble.csv"
    original = path.read_bytes()
    changed = original.replace(b"Exported 08/12/2026", b"Exported 08/13/2026")

    first = parse_csv_file(filename=path.name, content=original, broker=BrokerKind.SCHWAB)
    second = parse_csv_file(filename=path.name, content=changed, broker=BrokerKind.SCHWAB)

    assert [record.fingerprint for record in first.records] == [
        record.fingerprint for record in second.records
    ]
