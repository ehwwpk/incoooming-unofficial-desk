from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from schwab_dashboard.application.imports.csv_text import (
    CsvText,
    decimal_cell,
    header_key,
    row_dict,
    validate_headers,
)
from schwab_dashboard.application.imports.errors import CsvImportError
from schwab_dashboard.application.imports.option_normalizer import (
    contract_multiplier,
    option_metadata,
)
from schwab_dashboard.application.market_time import MARKET_TIME_ZONE
from schwab_dashboard.domain.data_source import (
    BrokerKind,
    ImportRecordKind,
    ImportRowDisposition,
    ParsedCsvFile,
    ParsedImportRecord,
    ParsedImportRow,
)

ZERO = Decimal("0")
_IBKR_SECTIONS = {
    "statement": "Statement",
    "trades": "Trades",
    "openpositions": "Open Positions",
    "cashtransactions": "Cash Transactions",
}


def is_ibkr_statement(table: CsvText) -> bool:
    return any(
        len(row) >= 2
        and _section_name(row[0]) in _IBKR_SECTIONS.values()
        and header_key(row[1]) in {"header", "data"}
        for row in table.rows[:30]
    )


def parse_ibkr_statement(
    *, filename: str, table: CsvText, digest: str, requested_broker: BrokerKind
) -> ParsedCsvFile:
    section_headers: dict[str, tuple[str, ...]] = {}
    records: list[ParsedImportRecord] = []
    outcomes: list[ParsedImportRow] = []
    counts: Counter[str] = Counter()
    capabilities: set[str] = set()
    warnings: list[str] = []
    if requested_broker not in {BrokerKind.IBKR, BrokerKind.GENERIC}:
        warnings.append(
            f"Selected {requested_broker.value.title()}, but this is an IBKR "
            "multi-section statement."
        )
    for row_number, row in enumerate(table.rows, start=1):
        if not any(row):
            continue
        section = _section_name(row[0]) if row else ""
        marker = header_key(row[1]) if len(row) > 1 else ""
        if marker == "header":
            section_header = tuple(row[2:])
            validate_headers(section_header)
            section_headers[section] = section_header
            outcomes.append(
                _row(row_number, row, ImportRowDisposition.IGNORED, "IBKR section header.")
            )
            continue
        if marker != "data":
            outcomes.append(
                _row(row_number, row, ImportRowDisposition.IGNORED, "IBKR statement metadata.")
            )
            continue
        current_headers = section_headers.get(section)
        if current_headers is None:
            outcomes.append(
                _row(
                    row_number,
                    row,
                    ImportRowDisposition.REJECTED,
                    "IBKR data appeared before its section header.",
                )
            )
            continue
        if len(row[2:]) > len(current_headers):
            outcomes.append(
                _row(
                    row_number,
                    row,
                    ImportRowDisposition.REJECTED,
                    "Row has more cells than its IBKR section header; check CSV quoting.",
                )
            )
            continue
        raw = row_dict(current_headers, row[2:])
        try:
            parsed = _parse_section(section, raw)
        except CsvImportError as exc:
            outcomes.append(
                ParsedImportRow(row_number, ImportRowDisposition.REJECTED, raw, str(exc))
            )
            continue
        if parsed is None:
            outcomes.append(
                ParsedImportRow(
                    row_number,
                    ImportRowDisposition.IGNORED,
                    raw,
                    f"IBKR {section} row is not part of the supported ledger surface.",
                )
            )
            continue
        kind, normalized, capability = parsed
        capabilities.add(capability)
        fingerprint = _fingerprint(kind, normalized)
        counts[fingerprint] += 1
        suffix = f":{counts[fingerprint]}" if counts[fingerprint] > 1 else ""
        record = ParsedImportRecord(
            kind=kind,
            external_key=f"csv:{fingerprint}{suffix}",
            fingerprint=fingerprint,
            source_row_number=row_number,
            normalized=normalized,
            raw=raw,
        )
        records.append(record)
        outcomes.append(
            ParsedImportRow(row_number, ImportRowDisposition.IMPORTED, raw, record=record)
        )
    if not records:
        raise CsvImportError(
            "The IBKR statement contained no supported trade, position, or cash rows."
        )
    rejected = sum(item.disposition is ImportRowDisposition.REJECTED for item in outcomes)
    if rejected:
        warnings.append(f"{rejected} IBKR row(s) were rejected; none entered the ledger.")
    warnings.append(
        "IBKR Flex and custom Activity Statements vary; preview every section before import."
    )
    return ParsedCsvFile(
        filename=Path(filename).name or "ibkr-statement.csv",
        file_kind="statement",
        headers=tuple(section_headers.keys()),
        records=tuple(records),
        rows=tuple(outcomes),
        warnings=tuple(warnings),
        sha256=digest,
        detected_broker=BrokerKind.IBKR,
        profile="ibkr-activity-statement",
        confidence="high",
        header_row=1,
        encoding=table.encoding,
        delimiter=table.delimiter,
        capabilities=tuple(sorted(capabilities)),
    )


def _parse_section(
    section: str, raw: dict[str, str]
) -> tuple[ImportRecordKind, dict[str, object], str] | None:
    if section == "Trades":
        category = _get(raw, "Asset Category").upper()
        if category not in {"STOCKS", "OPTIONS", "EQUITY AND INDEX OPTIONS"}:
            return None
        is_option = category in {"OPTIONS", "EQUITY AND INDEX OPTIONS"}
        symbol = _get(raw, "Symbol").upper()
        if not symbol:
            raise CsvImportError("IBKR trade symbol is blank")
        description = _get(raw, "Description") or symbol
        option = option_metadata(symbol=symbol, description=description) if is_option else None
        if is_option and option is None:
            raise CsvImportError("IBKR option trade has no recognizable contract identity")
        quantity_signed = _number(_get(raw, "Quantity"), required=True) or ZERO
        if quantity_signed == ZERO:
            raise CsvImportError("IBKR trade quantity must be nonzero")
        if is_option and quantity_signed != quantity_signed.to_integral_value():
            raise CsvImportError("IBKR option trade quantity is not a whole contract count")
        quantity = abs(quantity_signed)
        price = abs(_number(_get(raw, "T. Price", "Trade Price"), required=True) or ZERO)
        proceeds = _number(_get(raw, "Proceeds"))
        commission = _number(_get(raw, "Comm/Fee", "Commission")) or ZERO
        fees = max(ZERO, -commission)
        explicit_multiplier = _number(_get(raw, "Mult", "Multiplier"))
        multiplier, multiplier_source = contract_multiplier(
            explicit=explicit_multiplier,
            symbol=symbol,
            description=description,
            is_option=is_option,
        )
        if is_option and multiplier is None and proceeds is None:
            raise CsvImportError("IBKR option trade has no reliable multiplier or gross proceeds")
        gross = (
            quantity * price * (multiplier or Decimal("1"))
            if not is_option or multiplier is not None
            else abs(proceeds or ZERO)
        )
        side = "buy" if quantity_signed > 0 else "sell"
        net_cash = (
            proceeds + commission
            if proceeds is not None
            else (gross if side == "sell" else -gross) - fees
        )
        normalized: dict[str, object] = {
            "external_key": "pending",
            "order_external_key": _get(raw, "Order ID", "OrderID") or None,
            "occurred_at": _date(_get(raw, "Date/Time", "TradeDate")).isoformat(),
            "side": side,
            "position_effect": _position_effect(_get(raw, "Code", "Codes")),
            "quantity": str(quantity),
            "price": str(price),
            "gross_amount": str(gross),
            "fees": str(fees),
            "net_cash": str(net_cash),
            "account_mask": _account_mask(raw),
            "symbol": option["occ_symbol"] if option else symbol,
            "description": description,
            "asset_type": "OPTION" if is_option else "EQUITY",
            "underlying_symbol": option["underlying_symbol"] if option else None,
            "option_type": option["option_type"] if option else None,
            "expiration_date": option["expiration_date"] if option else None,
            "strike": option["strike"] if option else None,
            "contract_multiplier": _text(multiplier) if is_option else None,
            "multiplier_source": multiplier_source if is_option else None,
        }
        return ImportRecordKind.EXECUTION, normalized, "executions"
    if section == "Open Positions":
        category = _get(raw, "Asset Category").upper()
        if category not in {"STOCKS", "OPTIONS", "EQUITY AND INDEX OPTIONS"}:
            return None
        is_option = category in {"OPTIONS", "EQUITY AND INDEX OPTIONS"}
        symbol = _get(raw, "Symbol").upper()
        if not symbol:
            raise CsvImportError("IBKR position symbol is blank")
        description = _get(raw, "Description") or symbol
        option = option_metadata(symbol=symbol, description=description) if is_option else None
        if is_option and option is None:
            raise CsvImportError("IBKR option position has no recognizable contract identity")
        quantity = _number(_get(raw, "Quantity"), required=True) or ZERO
        if quantity == ZERO:
            raise CsvImportError("IBKR position quantity must be nonzero")
        if is_option and quantity != quantity.to_integral_value():
            raise CsvImportError("IBKR option position quantity is not a whole contract count")
        position_multiplier, multiplier_source = contract_multiplier(
            explicit=_number(_get(raw, "Mult", "Multiplier")),
            symbol=symbol,
            description=description,
            is_option=is_option,
        )
        if is_option and position_multiplier is None:
            raise CsvImportError("IBKR option position has no reliable exported multiplier")
        normalized = {
            "account_mask": _account_mask(raw),
            "symbol": option["occ_symbol"] if option else symbol,
            "description": description,
            "asset_type": "OPTION" if is_option else "EQUITY",
            "quantity": str(quantity),
            "average_price": _text(_number(_get(raw, "Cost Price"))),
            "mark": _text(_number(_get(raw, "Close Price", "Mark Price"))),
            "market_value": _text(_number(_get(raw, "Value"))),
            "day_profit_loss": None,
            "day_profit_loss_percent": None,
            "strategy": "Short option" if option and quantity < 0 else None,
            "underlying_symbol": option["underlying_symbol"] if option else None,
            "option_type": option["option_type"] if option else None,
            "expiration_date": option["expiration_date"] if option else None,
            "strike": option["strike"] if option else None,
            "open_profit_loss": _text(_number(_get(raw, "Unrealized P/L"))),
            "contract_multiplier": _text(position_multiplier),
            "multiplier_source": multiplier_source if is_option else None,
        }
        return ImportRecordKind.POSITION, normalized, "positions"
    if section == "Cash Transactions":
        description = _get(raw, "Description", "Type")
        kind = _cash_type(description)
        if kind is None:
            return None
        amount = _number(_get(raw, "Amount"), required=True) or ZERO
        amount = _directional_cash_movement(amount, kind=kind, description=description)
        normalized = {
            "external_key": "pending",
            "occurred_at": _date(_get(raw, "Date/Time", "Date")).isoformat(),
            "movement_type": kind,
            "amount": str(amount),
            "description": description,
            "account_mask": _account_mask(raw),
            "symbol": _get(raw, "Symbol") or None,
            "underlying_symbol": _get(raw, "Symbol") or None,
        }
        return (
            ImportRecordKind.CASH_MOVEMENT,
            normalized,
            "dividends" if kind == "dividend" else "cash",
        )
    return None


def _cash_type(value: str) -> str | None:
    upper = value.upper()
    if "WITHHOLD" in upper or "TAX" in upper:
        return "withholding"
    if "FEE" in upper or "COMMISSION" in upper:
        return "fee"
    if "INTEREST" in upper:
        return "interest"
    if "DIVIDEND" in upper:
        return "dividend"
    if "DEPOSIT" in upper or "WITHDRAWAL" in upper:
        return "transfer"
    # IBKR reports internal and account transfers separately. A description
    # containing only "transfer" does not prove an external owner flow.
    return "other"


def _directional_cash_movement(
    amount: Decimal,
    *,
    kind: str,
    description: str,
) -> Decimal:
    """Normalize statement rows only when their category proves direction."""

    if kind in {"fee", "withholding"}:
        return -abs(amount)
    if kind != "transfer":
        return amount
    upper = description.upper()
    if "WITHDRAW" in upper:
        return -abs(amount)
    if "DEPOSIT" in upper:
        return abs(amount)
    return amount


def _position_effect(value: str) -> str:
    codes = {token.upper() for token in value.replace(";", " ").replace(",", " ").split()}
    if "O" in codes and "C" not in codes:
        return "opening"
    if "C" in codes and "O" not in codes:
        return "closing"
    return "unknown"


def _date(value: str) -> datetime:
    cleaned = value.strip().replace(";", " ")
    for pattern in ("%Y-%m-%d, %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(cleaned, pattern).replace(tzinfo=MARKET_TIME_ZONE)
        except ValueError:
            pass
    raise CsvImportError(f"IBKR date {value!r} is not recognized")


def _number(value: str, *, required: bool = False) -> Decimal | None:
    return decimal_cell(value, required=required, label="IBKR number")


def _get(raw: dict[str, str], *names: str) -> str:
    normalized = {header_key(header): value for header, value in raw.items()}
    for name in names:
        if (value := normalized.get(header_key(name))) is not None:
            return value.strip()
    return ""


def _section_name(value: str) -> str:
    stripped = value.strip()
    return _IBKR_SECTIONS.get(header_key(stripped), stripped)


def _account_mask(raw: dict[str, str]) -> str:
    value = _get(raw, "Account ID", "Client Account ID", "Account")
    compact = "".join(character for character in value if character.isalnum())
    return f"...{compact[-4:]}" if any(character.isdigit() for character in compact) else "...IBKR"


def _fingerprint(kind: ImportRecordKind, normalized: dict[str, object]) -> str:
    body = json.dumps(
        {"kind": kind.value, "record": normalized}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(body.encode()).hexdigest()[:32]


def _row(
    number: int, row: tuple[str, ...], disposition: ImportRowDisposition, reason: str
) -> ParsedImportRow:
    return ParsedImportRow(number, disposition, {"_line": " | ".join(row)}, reason)


def _text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None
