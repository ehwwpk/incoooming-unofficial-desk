from __future__ import annotations

from schwab_dashboard.application.imports import CsvImportError, parse_csv_file
from schwab_dashboard.domain.data_source import ImportRecordKind

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


def test_positions_csv_preserves_exported_values_without_inventing_profit_loss() -> None:
    parsed = parse_csv_file(
        filename="positions.csv",
        content=POSITIONS,
    )

    assert parsed.file_kind == "positions"
    assert len(parsed.records) == 2
    equity, option = parsed.records
    assert equity.kind is ImportRecordKind.POSITION
    assert equity.normalized["account_mask"] == "...4321"
    assert equity.normalized["open_profit_loss"] == "4500.00"
    assert option.normalized["asset_type"] == "OPTION"
    assert option.normalized["underlying_symbol"] == "CVX"
    assert option.normalized["option_type"] == "CALL"
    assert option.normalized["strike"] == "205"
    assert option.normalized["open_profit_loss"] == "75.00"


def test_activity_csv_separates_executions_and_dividends() -> None:
    parsed = parse_csv_file(
        filename="activity.csv",
        content=ACTIVITY,
    )

    assert [item.kind for item in parsed.records] == [
        ImportRecordKind.EXECUTION,
        ImportRecordKind.CASH_MOVEMENT,
    ]
    assert parsed.records[0].normalized["net_cash"] == "124.97"
    assert parsed.records[1].normalized["movement_type"] == "dividend"
    assert parsed.records[1].normalized["amount"] == "171.00"


def test_csv_import_fails_closed_on_unknown_shape() -> None:
    try:
        parse_csv_file(
            filename="mystery.csv",
            content=b"foo,bar\n1,2\n",
        )
    except CsvImportError as exc:
        assert "header" in str(exc).lower()
    else:
        raise AssertionError("unsupported CSV shape must fail closed")
