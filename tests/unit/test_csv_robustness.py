from __future__ import annotations

import csv
import io

import pytest

from schwab_dashboard.application.imports import CsvImportError, parse_csv_file
from schwab_dashboard.application.imports.csv_text import (
    HEADER_SCAN_ROWS,
    MAX_CSV_BYTES,
    MAX_CSV_ROWS,
    read_csv_text,
)
from schwab_dashboard.application.option_lifecycle import delivered_share_quantity
from schwab_dashboard.domain.data_source import BrokerKind, ImportRecordKind


def _csv_bytes(rows: list[list[str]], *, delimiter: str = ",", encoding: str = "utf-8") -> bytes:
    stream = io.StringIO(newline="")
    csv.writer(stream, delimiter=delimiter, lineterminator="\r\n").writerows(rows)
    return stream.getvalue().encode(encoding)


def test_alias_headers_are_a_structural_contract_not_fixture_literals() -> None:
    content = _csv_bytes(
        [
            [
                "Memo",
                "Net Amount",
                "Security Symbol",
                "Trade Date",
                "Transaction Type",
                "Qty",
                "Trade Price",
                "Account Number",
                "Security Description",
                "Commission & Fees",
            ],
            [
                "variant export",
                "124.97",
                "CVX  260821C00205000",
                "08/01/2026",
                "Sell to Open",
                "1",
                "1.25",
                "Brokerage 4321",
                "CVX 08/21/2026 205 Call",
                "0.03",
            ],
        ],
        delimiter=";",
    )

    parsed = parse_csv_file(filename="renamed-columns.csv", content=content)

    assert parsed.detected_broker is BrokerKind.GENERIC
    assert parsed.confidence == "medium"
    assert parsed.delimiter == ";"
    assert parsed.records[0].kind is ImportRecordKind.EXECUTION
    assert parsed.records[0].normalized["account_mask"] == "...4321"
    assert parsed.records[0].normalized["net_cash"] == "124.97"


def test_reordered_position_aliases_parse_from_utf16_tab_export() -> None:
    content = _csv_bytes(
        [
            [
                "Current Value",
                "Security Description",
                "Qty",
                "Ticker",
                "Account Number",
                "Current Price",
            ],
            ["19500.00", "Chevron Corp", "100", "CVX", "Brokerage 4321", "195.00"],
        ],
        delimiter="\t",
        encoding="utf-16",
    )

    parsed = parse_csv_file(filename="positions.csv", content=content)

    assert parsed.encoding == "utf-16"
    assert parsed.delimiter == "\t"
    assert parsed.records[0].normalized["symbol"] == "CVX"
    assert parsed.records[0].normalized["market_value"] == "19500.00"


@pytest.mark.parametrize(
    ("delimiter", "encoding"),
    ((",", "utf-8-sig"), ("\t", "utf-16"), (";", "cp1252")),
)
def test_supported_delimiters_encodings_quotes_and_line_endings(
    delimiter: str, encoding: str
) -> None:
    description = "Caf\N{LATIN SMALL LETTER E WITH ACUTE} dividend, class A"
    content = _csv_bytes(
        [
            ["Account", "Date", "Action", "Symbol", "Description", "Amount"],
            ["Brokerage 4321", "08/02/2026", "Dividend", "CVX", description, "171.00"],
        ],
        delimiter=delimiter,
        encoding=encoding,
    )

    parsed = parse_csv_file(filename="activity.csv", content=content)

    assert parsed.delimiter == delimiter
    assert parsed.records[0].normalized["description"] == description
    assert parsed.records[0].normalized["amount"] == "171.00"


def test_column_order_and_irrelevant_columns_do_not_change_the_record() -> None:
    values = {
        "Account": "Brokerage 4321",
        "Date": "08/01/2026",
        "Action": "Sell to Open",
        "Symbol": "CVX  260821C00205000",
        "Description": "CVX 08/21/2026 205 Call",
        "Quantity": "1",
        "Price": "1.25",
        "Fees": "0.03",
        "Amount": "124.97",
        "Unused Broker Note": "not part of the normalized ledger",
    }
    headers = list(values)
    orders = [
        headers,
        list(reversed(headers)),
        headers[3:] + headers[:3],
        headers[::2] + headers[1::2],
    ]
    normalized: list[dict[str, object]] = []
    for order in orders:
        parsed = parse_csv_file(
            filename="activity.csv",
            content=_csv_bytes([order, [values[column] for column in order]]),
        )
        normalized.append(parsed.records[0].normalized)

    assert normalized[1:] == normalized[:-1]


@pytest.mark.parametrize(
    "bad_number",
    ("NaN", "Infinity", "-Infinity", "1,25", "10%", "1e3", "(1.00", "1.2.3"),
)
def test_unsafe_numbers_reject_only_the_bad_row(bad_number: str) -> None:
    content = _csv_bytes(
        [
            ["Account", "Symbol", "Quantity", "Last Price", "Market Value"],
            ["Brokerage 4321", "CVX", "100", "195.00", "19500.00"],
            ["Brokerage 4321", "BAD", bad_number, "1.00", "1.00"],
        ],
        delimiter=";",
    )

    parsed = parse_csv_file(filename="positions.csv", content=content)

    assert [record.normalized["symbol"] for record in parsed.records] == ["CVX"]
    assert parsed.rejected_count == 1
    assert "rejected" in " ".join(parsed.warnings).lower()


def test_us_grouped_currency_and_parentheses_remain_supported() -> None:
    content = _csv_bytes(
        [
            ["Account", "Symbol", "Quantity", "Last Price", "Market Value"],
            ["Brokerage 4321", "CVX", "100", "$195.25", "$19,525.00"],
            ["Brokerage 4321", "KTOS", "(25)", "$75.00", "($1,875.00)"],
        ],
        delimiter=";",
    )

    parsed = parse_csv_file(filename="positions.csv", content=content)

    assert parsed.records[0].normalized["market_value"] == "19525.00"
    assert parsed.records[1].normalized["quantity"] == "-25"
    assert parsed.records[1].normalized["market_value"] == "-1875.00"


@pytest.mark.parametrize("duplicate", ("SYMBOL!", "Ticker"))
def test_duplicate_equivalent_headers_fail_closed(duplicate: str) -> None:
    content = _csv_bytes(
        [
            ["Account", "Symbol", "Quantity", "Last Price", "Market Value", duplicate],
            ["Brokerage 4321", "CVX", "100", "195.00", "19500.00", "KTOS"],
        ]
    )

    with pytest.raises(CsvImportError, match=r"duplicate|ambiguous"):
        parse_csv_file(filename="positions.csv", content=content)


@pytest.mark.parametrize(
    "content",
    (
        b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj",
        b"PK\x03\x04not-a-csv-archive",
        bytes(range(256)),
        b"<html><body>Account statement</body></html>",
    ),
)
def test_non_csv_and_binary_inputs_fail_closed(content: bytes) -> None:
    with pytest.raises(CsvImportError, match=r"CSV|binary|header"):
        parse_csv_file(filename="statement.csv", content=content)


def test_html_disguised_as_recognized_columns_and_malformed_quotes_fail_closed() -> None:
    html = (
        b"<html>\n<Account>,<Symbol>,<Quantity>,<Last Price>,<Market Value>\n"
        b"Brokerage 4321,CVX,100,195.00,19500.00\n"
    )
    with pytest.raises(CsvImportError, match="not CSV"):
        parse_csv_file(filename="statement.csv", content=html)

    malformed = (
        b"Account,Symbol,Quantity,Last Price,Market Value\n"
        b'Brokerage 4321,CVX,100,195.00,"unterminated\n'
    )
    with pytest.raises(CsvImportError, match="structure"):
        parse_csv_file(filename="statement.csv", content=malformed)


def test_unquoted_extra_cells_are_rejected_instead_of_shifting_numeric_columns() -> None:
    content = (
        b"Account,Symbol,Quantity,Last Price,Market Value\n"
        b"Brokerage 4321,BAD,100,1,250,125000\n"
        b"Brokerage 4321,CVX,100,195,19500\n"
    )

    parsed = parse_csv_file(filename="positions.csv", content=content)

    assert [record.normalized["symbol"] for record in parsed.records] == ["CVX"]
    assert parsed.rejected_count == 1
    assert "check CSV quoting" in next(row.reason or "" for row in parsed.rows if row.reason)


def test_file_size_and_row_count_limits_are_enforced_before_normalization() -> None:
    with pytest.raises(CsvImportError, match="10 MB"):
        read_csv_text(b"x" * (MAX_CSV_BYTES + 1))

    too_many_rows = b"\n" * (MAX_CSV_ROWS + HEADER_SCAN_ROWS + 2)
    with pytest.raises(CsvImportError, match="data rows"):
        read_csv_text(too_many_rows)

    header = b"Account,Symbol,Quantity,Last Price,Market Value\n"
    row = b"Brokerage 4321,CVX,100,195.00,19500.00\n"
    with pytest.raises(CsvImportError, match="data rows"):
        parse_csv_file(filename="too-many.csv", content=header + row * (MAX_CSV_ROWS + 1))


def test_header_scan_boundary_is_explicit_and_bounded() -> None:
    header_and_row = (
        b"Account,Symbol,Quantity,Last Price,Market Value\nBrokerage 4321,CVX,100,195.00,19500.00\n"
    )
    accepted = parse_csv_file(
        filename="positions.csv",
        content=(b"metadata\n" * (HEADER_SCAN_ROWS - 1)) + header_and_row,
    )
    assert accepted.header_row == HEADER_SCAN_ROWS

    with pytest.raises(CsvImportError, match="first 30 rows"):
        parse_csv_file(
            filename="positions.csv",
            content=(b"metadata\n" * HEADER_SCAN_ROWS) + header_and_row,
        )


def test_ibkr_column_order_and_extra_fields_are_not_hardwired() -> None:
    content = _csv_bytes(
        [
            [
                " trades ",
                "HEADER",
                "Memo",
                " CODE! ",
                " COMM/FEE! ",
                " PROCEEDS! ",
                " T. PRICE! ",
                " QUANTITY! ",
                " DATE/TIME! ",
                " DESCRIPTION! ",
                " SYMBOL! ",
                " ASSET CATEGORY! ",
                "Broker Evidence",
            ],
            [
                "TRADES",
                "data",
                "variant",
                "O",
                "-0.03",
                "125",
                "1.25",
                "-1",
                "2026-08-01 10:30:00",
                "CVX option",
                "CVX  260821C00205000",
                "Options",
                "headed trailing evidence",
            ],
        ]
    )

    parsed = parse_csv_file(filename="statement.csv", content=content, broker=BrokerKind.IBKR)

    assert parsed.records[0].normalized["net_cash"] == "124.97"
    assert parsed.records[0].raw["Memo"] == "variant"
    assert parsed.records[0].raw["Broker Evidence"] == "headed trailing evidence"


@pytest.mark.parametrize("bad_number", ("NaN", "Infinity", "1,25", "10%", "1e3"))
def test_ibkr_unsafe_numbers_are_row_rejections_not_import_crashes(bad_number: str) -> None:
    content = _csv_bytes(
        [
            [
                "Trades",
                "Header",
                "Asset Category",
                "Symbol",
                "Description",
                "Date/Time",
                "Quantity",
                "T. Price",
                "Proceeds",
                "Comm/Fee",
                "Mult",
                "Code",
            ],
            [
                "Trades",
                "Data",
                "Stocks",
                "BAD",
                "Unsafe numeric row",
                "2026-08-01 10:30:00",
                bad_number,
                "1.00",
                "1.00",
                "0",
                "1",
                "O",
            ],
            ["Cash Transactions", "Header", "Date/Time", "Description", "Amount", "Symbol"],
            [
                "Cash Transactions",
                "Data",
                "2026-08-02",
                "Dividend",
                "10.00",
                "CVX",
            ],
        ]
    )

    parsed = parse_csv_file(filename="statement.csv", content=content, broker=BrokerKind.IBKR)

    assert [record.kind for record in parsed.records] == [ImportRecordKind.CASH_MOVEMENT]
    assert parsed.rejected_count == 1


def test_current_schwab_position_headers_are_recognized_without_generic_downgrade() -> None:
    content = _csv_bytes(
        [
            [
                "Symbol",
                "Quantity",
                "Current Price",
                "Market Value",
                "Cost per Share",
                "P&L $",
                "P&L %",
            ],
            ["CVX", "100", "195.00", "19500.00", "150.00", "4500.00", "30.00"],
        ]
    )

    parsed = parse_csv_file(filename="positions.csv", content=content, broker=BrokerKind.SCHWAB)

    assert parsed.detected_broker is BrokerKind.SCHWAB
    assert parsed.confidence == "high"
    assert parsed.records[0].normalized["average_price"] == "150.00"
    assert parsed.records[0].normalized["open_profit_loss"] == "4500.00"


def test_currency_and_percent_headers_are_distinct_and_only_cash_pl_is_imported() -> None:
    content = _csv_bytes(
        [
            ["Account", "Symbol", "Quantity", "Current Price $", "Market Value $", "P&L %"],
            ["Brokerage 4321", "CVX", "100", "195.00", "19500.00", "30.00"],
        ]
    )

    parsed = parse_csv_file(filename="positions.csv", content=content)

    assert parsed.records[0].normalized["mark"] == "195.00"
    assert parsed.records[0].normalized["market_value"] == "19500.00"
    assert parsed.records[0].normalized["open_profit_loss"] is None


def test_position_market_value_follows_signed_quantity_not_unsigned_liability_display() -> None:
    content = _csv_bytes(
        [
            ["Account", "Symbol", "Description", "Quantity", "Last Price", "Market Value"],
            [
                "Brokerage 4321",
                "CVX  260821C00205000",
                "CVX 08/21/2026 205 Call",
                "-1",
                "1.25",
                "125.00",
            ],
        ]
    )

    parsed = parse_csv_file(filename="positions.csv", content=content)

    assert parsed.records[0].normalized["market_value"] == "-125.00"


def test_current_fidelity_position_headers_prefer_account_number() -> None:
    content = _csv_bytes(
        [
            [
                "Account Name",
                "Account Number",
                "Symbol",
                "Quantity",
                "Most Recent Price",
                "Most Recent Value",
                "Cost Basis Per Share",
            ],
            ["Brokerage", "Z12345678", "CVX", "100", "195.00", "19500.00", "150.00"],
        ]
    )

    parsed = parse_csv_file(filename="positions.csv", content=content, broker=BrokerKind.FIDELITY)

    assert parsed.detected_broker is BrokerKind.FIDELITY
    assert parsed.confidence == "high"
    assert parsed.records[0].normalized["account_mask"] == "...5678"
    assert parsed.records[0].normalized["mark"] == "195.00"
    assert parsed.records[0].normalized["market_value"] == "19500.00"
    assert parsed.records[0].normalized["average_price"] == "150.00"


def test_webull_uses_filled_quantity_when_total_quantity_has_a_generic_name() -> None:
    content = _csv_bytes(
        [
            ["Filled Time", "Symbol", "Side", "Filled", "Quantity", "Avg Price", "Status"],
            ["08/01/2026 10:31:00", "CVX", "SELL", "25", "100", "195.00", "Cancelled"],
        ]
    )

    parsed = parse_csv_file(filename="orders.csv", content=content, broker=BrokerKind.WEBULL)

    assert parsed.records[0].normalized["quantity"] == "25"


@pytest.mark.parametrize(
    ("description", "side", "strike"),
    (
        ("CVX 08/21/2026 CALL $205", "CALL", "205"),
        ("CVX AUG 21 2026 PUT $185", "PUT", "185"),
        ("CVX 21AUG26 205 C", "CALL", "205"),
        ("CVX 21 AUG 2026 P $190", "PUT", "190"),
    ),
)
def test_option_descriptions_accept_unambiguous_broker_word_orders(
    description: str, side: str, strike: str
) -> None:
    content = _csv_bytes(
        [
            ["Account", "Symbol", "Description", "Quantity", "Last Price", "Market Value"],
            ["Brokerage 4321", "CVX OPTION", description, "-1", "1.25", "-125.00"],
        ]
    )

    parsed = parse_csv_file(filename="positions.csv", content=content)
    option = parsed.records[0].normalized

    assert option["asset_type"] == "OPTION"
    assert option["option_type"] == side
    assert option["strike"] == strike
    assert option["expiration_date"] == "2026-08-21"


def test_equivalent_occ_spacing_has_one_canonical_identity() -> None:
    headers = ["Account", "Symbol", "Description", "Quantity", "Last Price", "Market Value"]
    rows = (
        ["Brokerage 4321", "CVX  260821C00205000", "CVX call", "-1", "1.25", "-125.00"],
        ["Brokerage 4321", "CVX260821C00205000", "CVX call", "-1", "1.25", "-125.00"],
    )

    parsed = [
        parse_csv_file(filename="positions.csv", content=_csv_bytes([headers, row])) for row in rows
    ]

    assert parsed[0].records[0].normalized["symbol"] == "CVX   260821C00205000"
    assert parsed[0].records[0].normalized == parsed[1].records[0].normalized
    assert parsed[0].records[0].fingerprint == parsed[1].records[0].fingerprint


@pytest.mark.parametrize(
    "bad_description",
    (
        "CVX 02/30/2026 205 CALL",
        "CVX FEB 30 2026 CALL $205",
        "CVX 30FEB26 205 C",
        "TOOLONGROOT 08/21/2026 205 CALL",
        "CVX 08/21/2026 205.1234 CALL",
    ),
)
def test_malformed_option_identity_is_held_for_review_not_treated_as_equity(
    bad_description: str,
) -> None:
    content = _csv_bytes(
        [
            ["Account", "Symbol", "Description", "Quantity", "Last Price", "Market Value"],
            ["Brokerage 4321", "BAD OPTION", bad_description, "-1", "1.25", "-125.00"],
            ["Brokerage 4321", "CVX", "Chevron Corp", "100", "195.00", "19500.00"],
        ]
    )

    parsed = parse_csv_file(filename="positions.csv", content=content)

    assert [record.normalized["symbol"] for record in parsed.records] == ["CVX"]
    assert parsed.review_count == 1
    assert "contract identity" in next(row.reason or "" for row in parsed.rows if row.reason)


def test_invalid_dated_c_or_p_description_cannot_fall_through_as_stock() -> None:
    content = _csv_bytes(
        [
            ["Account", "Symbol", "Description", "Quantity", "Last Price", "Market Value"],
            ["Brokerage 4321", "CVX", "CVX 02/30/2026 205 C", "-1", "1.25", "-125.00"],
            ["Brokerage 4321", "KTOS", "Kratos", "100", "75", "7500"],
        ]
    )

    parsed = parse_csv_file(filename="positions.csv", content=content)

    assert [record.normalized["symbol"] for record in parsed.records] == ["KTOS"]
    assert parsed.review_count == 1


def test_unsafe_execution_rows_do_not_enter_the_ledger() -> None:
    content = _csv_bytes(
        [
            ["Account", "Date", "Action", "Symbol", "Description", "Quantity", "Price", "Amount"],
            ["Brokerage", "08/01/2026", "Sell", "", "blank symbol", "1", "10", "10"],
            ["Brokerage", "08/01/2026", "Sell", "CVX", "zero quantity", "0", "10", "0"],
            [
                "Brokerage",
                "08/21/2026",
                "Expired",
                "CVX  260821C00205000",
                "CVX 08/21/2026 205 Call",
                "",
                "",
                "",
            ],
            ["Brokerage", "08/02/2026", "Dividend", "CVX", "Chevron dividend", "", "", "25"],
        ]
    )

    parsed = parse_csv_file(filename="activity.csv", content=content)

    assert [record.kind for record in parsed.records] == [ImportRecordKind.CASH_MOVEMENT]
    assert parsed.rejected_count == 2
    assert parsed.review_count == 1
    assert parsed.records[0].normalized["account_mask"] == "...CSV"


@pytest.mark.parametrize(
    "description", ("Machinery adjustment", "Coffee rebate", "Wireless refund")
)
def test_cash_classification_uses_words_not_dangerous_substrings(description: str) -> None:
    content = _csv_bytes(
        [
            ["Account", "Date", "Action", "Symbol", "Description", "Amount"],
            ["Brokerage 4321", "08/02/2026", "Adjustment", "", description, "25"],
        ]
    )

    parsed = parse_csv_file(filename="activity.csv", content=content)

    assert parsed.records[0].normalized["movement_type"] == "other"


def test_adjusted_lifecycle_keeps_exported_multiplier_and_delivered_shares() -> None:
    content = _csv_bytes(
        [
            [
                "Account",
                "Date",
                "Action",
                "Symbol",
                "Description",
                "Quantity",
                "Stock Quantity",
                "Price",
                "Amount",
                "Multiplier",
            ],
            [
                "Brokerage 4321",
                "08/21/2026",
                "Assigned",
                "XYZ1  260821C00050000",
                "Adjusted option assignment",
                "1",
                "150",
                "0",
                "0",
                "150",
            ],
        ]
    )

    parsed = parse_csv_file(filename="activity.csv", content=content)
    event = parsed.records[0].normalized

    assert event["event_type"] == "assignment"
    assert event["contract_multiplier"] == "150"
    assert event["stock_quantity"] == "150"
    assert delivered_share_quantity(event) == 150


def test_adjusted_lifecycle_without_deliverable_evidence_is_held_for_review() -> None:
    content = _csv_bytes(
        [
            [
                "Account",
                "Date",
                "Action",
                "Symbol",
                "Description",
                "Quantity",
                "Price",
                "Amount",
            ],
            [
                "Brokerage 4321",
                "08/21/2026",
                "Assigned",
                "XYZ1  260821C00050000",
                "Adjusted option assignment",
                "1",
                "0",
            ],
            ["Brokerage 4321", "08/02/2026", "Dividend", "XYZ", "Dividend", "", "", "10"],
        ]
    )

    parsed = parse_csv_file(filename="activity.csv", content=content)

    assert [record.kind for record in parsed.records] == [ImportRecordKind.CASH_MOVEMENT]
    assert parsed.review_count == 1
    assert "no exported multiplier or delivered shares" in next(
        row.reason or "" for row in parsed.rows if row.reason
    )


def test_lifecycle_can_derive_whole_contracts_from_delivered_shares() -> None:
    content = _csv_bytes(
        [
            [
                "Account",
                "Date",
                "Action",
                "Symbol",
                "Description",
                "Quantity",
                "Stock Quantity",
                "Price",
            ],
            [
                "Brokerage 4321",
                "08/21/2026",
                "Assigned",
                "CVX  260821C00205000",
                "CVX 08/21/2026 205 Call",
                "",
                "200",
                "0",
            ],
        ]
    )

    parsed = parse_csv_file(filename="activity.csv", content=content)

    assert parsed.records[0].normalized["option_quantity"] == "2"
    assert parsed.records[0].normalized["stock_quantity"] == "200"


def test_fractional_option_contracts_are_held_for_review() -> None:
    content = _csv_bytes(
        [
            ["Account", "Symbol", "Description", "Quantity", "Last Price", "Market Value"],
            [
                "Brokerage 4321",
                "CVX  260821C00205000",
                "CVX 08/21/2026 205 Call",
                "-1.5",
                "1.25",
                "-187.50",
            ],
            ["Brokerage 4321", "CVX", "Chevron", "100.5", "195", "19597.50"],
        ]
    )

    parsed = parse_csv_file(filename="positions.csv", content=content)

    assert parsed.records[0].normalized["quantity"] == "100.5"
    assert parsed.review_count == 1


def test_ibkr_blank_symbols_and_zero_quantities_are_rejected_per_row() -> None:
    content = _csv_bytes(
        [
            [
                "Trades",
                "Header",
                "Asset Category",
                "Symbol",
                "Description",
                "Date/Time",
                "Quantity",
                "T. Price",
                "Proceeds",
                "Comm/Fee",
            ],
            ["Trades", "Data", "Stocks", "", "blank", "2026-08-01", "1", "10", "10", "0"],
            ["Trades", "Data", "Stocks", "CVX", "zero", "2026-08-01", "0", "10", "0", "0"],
            ["Cash Transactions", "Header", "Date/Time", "Description", "Amount", "Symbol"],
            ["Cash Transactions", "Data", "2026-08-02", "Dividend", "10", "CVX"],
        ]
    )

    parsed = parse_csv_file(filename="statement.csv", content=content, broker=BrokerKind.IBKR)

    assert [record.kind for record in parsed.records] == [ImportRecordKind.CASH_MOVEMENT]
    assert parsed.rejected_count == 2


def test_ibkr_row_level_account_ids_remain_separate() -> None:
    content = _csv_bytes(
        [
            [
                "Trades",
                "Header",
                "Account ID",
                "Asset Category",
                "Symbol",
                "Description",
                "Date/Time",
                "Quantity",
                "T. Price",
                "Proceeds",
                "Comm/Fee",
            ],
            [
                "Trades",
                "Data",
                "U1234567",
                "Stocks",
                "CVX",
                "Chevron",
                "2026-08-01",
                "-1",
                "195",
                "195",
                "0",
            ],
            ["Cash Transactions", "Header", "Client Account ID", "Date", "Description", "Amount"],
            ["Cash Transactions", "Data", "U7654321", "2026-08-02", "Dividend", "10"],
        ]
    )

    parsed = parse_csv_file(filename="statement.csv", content=content, broker=BrokerKind.IBKR)

    assert [record.normalized["account_mask"] for record in parsed.records] == [
        "...4567",
        "...4321",
    ]


@pytest.mark.parametrize("extra", ("125000", "unheaded evidence"))
def test_ibkr_extra_cells_cannot_shift_values_into_the_ledger(extra: str) -> None:
    content = (
        "Open Positions,Header,Asset Category,Symbol,Quantity,Close Price,Value\n"
        f"Open Positions,Data,Stocks,BAD,100,1,250,{extra}\n"
        "Open Positions,Data,Stocks,CVX,100,195,19500\n"
    ).encode()

    parsed = parse_csv_file(filename="statement.csv", content=content, broker=BrokerKind.IBKR)

    assert [record.normalized["symbol"] for record in parsed.records] == ["CVX"]
    assert parsed.rejected_count == 1
    assert "check CSV quoting" in next(
        row.reason or "" for row in parsed.rows if row.disposition.value == "rejected"
    )


@pytest.mark.parametrize("description", ("XYZ1 08/21/2026 50 CALL", "XYZ1 21AUG26 50 C"))
def test_adjusted_root_from_description_needs_deliverable_evidence(description: str) -> None:
    content = _csv_bytes(
        [
            ["Account", "Symbol", "Description", "Quantity", "Last Price", "Market Value"],
            ["...4321", "XYZ1 OPTION", description, "-1", "1.25", "-125"],
            ["...4321", "CVX", "Chevron", "100", "195", "19500"],
        ]
    )

    parsed = parse_csv_file(filename="positions.csv", content=content)

    assert [record.normalized["symbol"] for record in parsed.records] == ["CVX"]
    assert parsed.review_count == 1
    assert any("multiplier" in (row.reason or "") for row in parsed.rows)


def test_adjusted_description_keeps_exported_cash_without_guessing_multiplier() -> None:
    content = _csv_bytes(
        [
            ["Account", "Date", "Action", "Symbol", "Description", "Quantity", "Price", "Amount"],
            [
                "...4321",
                "08/01/2026",
                "Sell to Open",
                "XYZ1 OPTION",
                "XYZ1 08/21/2026 50 CALL",
                "1",
                "1",
                "150",
            ],
        ]
    )

    parsed = parse_csv_file(filename="activity.csv", content=content)
    execution = parsed.records[0].normalized

    assert execution["contract_multiplier"] is None
    assert execution["multiplier_source"] == "unknown_adjusted"
    assert execution["net_cash"] == "150"
    assert execution["gross_amount"] == "150"


@pytest.mark.parametrize(
    ("action", "symbol", "description", "side", "amount"),
    (
        ("Buy", "SCHD", "Schwab US Dividend Equity ETF", "buy", "-3000"),
        ("YOU BOUGHT", "SCHD", "Schwab US Dividend Equity ETF", "buy", "-3000"),
        ("YOU SOLD", "PFIX", "Simplify Interest Rate Hedge ETF", "sell", "3000"),
        ("Buy", "QYLD", "Global X Nasdaq 100 Covered Call ETF", "buy", "-3000"),
        ("Sell", "PUTW", "WisdomTree PutWrite Strategy Fund", "sell", "3000"),
    ),
)
def test_named_fund_trades_stay_executions(
    action: str, symbol: str, description: str, side: str, amount: str
) -> None:
    content = _csv_bytes(
        [
            ["Account", "Date", "Action", "Symbol", "Description", "Quantity", "Price", "Amount"],
            ["...4321", "08/01/2026", action, symbol, description, "100", "30", amount],
        ]
    )

    parsed = parse_csv_file(filename="activity.csv", content=content)

    assert parsed.records[0].kind is ImportRecordKind.EXECUTION
    assert parsed.records[0].normalized["asset_type"] == "EQUITY"
    assert parsed.records[0].normalized["side"] == side
    assert parsed.records[0].normalized["net_cash"] == amount


def test_named_fund_holdings_are_equities_but_invalid_fund_options_need_review() -> None:
    content = _csv_bytes(
        [
            ["Account", "Symbol", "Description", "Quantity", "Last Price", "Market Value"],
            ["...4321", "QYLD", "Global X Nasdaq 100 Covered Call ETF", "100", "18", "1800"],
            ["...4321", "QYLD", "QYLD ETF 02/30/2026 18 CALL", "-1", "1", "-100"],
        ]
    )

    parsed = parse_csv_file(filename="positions.csv", content=content)

    assert len(parsed.records) == 1
    assert parsed.records[0].normalized["asset_type"] == "EQUITY"
    assert parsed.review_count == 1
