from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from schwab_dashboard.domain.data_source import (
    ImportRecordKind,
    ParsedCsvFile,
    ParsedImportRecord,
)
from schwab_dashboard.infrastructure.schwab.option_symbol import parse_occ_option_symbol

MAX_CSV_BYTES = 10 * 1024 * 1024
MAX_CSV_ROWS = 50_000
ZERO = Decimal("0")

_ALIASES = {
    "account": ("account", "accountnumber", "accountname", "accountnameor number"),
    "symbol": ("symbol", "instrument", "securitysymbol", "ticker"),
    "description": ("description", "securitydescription", "name"),
    "quantity": ("quantity", "qty", "shares", "position"),
    "mark": ("lastprice", "price", "currentprice", "mark"),
    "market_value": ("marketvalue", "currentvalue", "positiondollarvalue", "value"),
    "average_price": ("averageprice", "averagecostbasis", "costshare", "costpershare"),
    "cost_basis": ("costbasis", "costtotal", "totalcostbasis"),
    "day_profit_loss": (
        "daychangepl",
        "daychange",
        "todaysgainlossdollar",
        "daygainloss",
    ),
    "open_profit_loss": (
        "totalgainlossdollar",
        "totalgainloss",
        "openprofitloss",
        "unrealizedgainloss",
    ),
    "date": ("date", "activitydate", "rundate", "tradedate", "processdate"),
    "action": ("action", "transcode", "transactiontype", "type"),
    "price": ("price", "priceamount", "tradeprice"),
    "fees": ("feescomm", "fees", "commission", "commissionfees"),
    "amount": ("amount", "netamount", "cashamount"),
}

_OPTION_DESCRIPTION = re.compile(
    r"(?P<underlying>[A-Z][A-Z0-9.]{0,8})\s+"
    r"(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+"
    r"(?P<strike>\d+(?:\.\d+)?)\s*(?P<side>CALL|PUT|C|P)\b",
    re.IGNORECASE,
)


class CsvImportError(ValueError):
    pass


def parse_csv_file(
    *,
    filename: str,
    content: bytes,
) -> ParsedCsvFile:
    if not content:
        raise CsvImportError("The selected CSV file is empty.")
    if len(content) > MAX_CSV_BYTES:
        raise CsvImportError("CSV files are limited to 10 MB each.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvImportError("The CSV must use UTF-8 text encoding.") from exc
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise CsvImportError("The CSV does not contain a header row.")
    headers = tuple(str(value).strip() for value in reader.fieldnames)
    field_map = _field_map(headers)
    file_kind = _detect_file_kind(field_map)
    digest = hashlib.sha256(content).hexdigest()
    records: list[ParsedImportRecord] = []
    warnings: list[str] = []
    rejected = 0
    for index, raw_row in enumerate(reader, start=2):
        if index - 1 > MAX_CSV_ROWS:
            raise CsvImportError(f"CSV files are limited to {MAX_CSV_ROWS:,} data rows.")
        row = {str(key).strip(): str(value or "").strip() for key, value in raw_row.items()}
        if not any(row.values()):
            continue
        try:
            normalized = (
                _position_row(row, field_map=field_map)
                if file_kind == "positions"
                else _activity_row(row, field_map=field_map)
            )
        except CsvImportError as exc:
            rejected += 1
            if len(warnings) < 8:
                warnings.append(f"Row {index}: {exc}")
            continue
        if normalized is None:
            continue
        kind, payload = normalized
        records.append(
            ParsedImportRecord(
                kind=kind,
                external_key=f"csv:{digest[:16]}:{index}",
                normalized=payload,
                raw=row,
            )
        )
    if not records:
        raise CsvImportError(
            "No supported position or activity rows were found. "
            "Use the downloadable template or check the selected file."
        )
    if rejected:
        warnings.insert(0, f"{rejected} row(s) could not be normalized and were not imported.")
    return ParsedCsvFile(
        filename=Path(filename).name or "import.csv",
        file_kind=file_kind,
        headers=headers,
        records=tuple(records),
        rejected_count=rejected,
        warnings=tuple(warnings),
        sha256=digest,
    )


def _field_map(headers: tuple[str, ...]) -> dict[str, str]:
    normalized = {_header_key(header): header for header in headers}
    result: dict[str, str] = {}
    for canonical, aliases in _ALIASES.items():
        for alias in aliases:
            match = normalized.get(_header_key(alias))
            if match is not None:
                result[canonical] = match
                break
    return result


def _detect_file_kind(field_map: dict[str, str]) -> str:
    if {"date", "action"} <= field_map.keys() and (
        "amount" in field_map or {"quantity", "price"} <= field_map.keys()
    ):
        return "activity"
    if {"symbol", "quantity"} <= field_map.keys() and (
        "market_value" in field_map or "mark" in field_map
    ):
        return "positions"
    raise CsvImportError(
        "The header is not a supported positions or activity export. "
        "Positions need symbol, quantity, and price/value; activity needs date and action."
    )


def _position_row(
    row: dict[str, str],
    *,
    field_map: dict[str, str],
) -> tuple[ImportRecordKind, dict[str, object]] | None:
    symbol = _value(row, field_map, "symbol").strip().upper()
    description = _value(row, field_map, "description") or symbol
    if not symbol or symbol in {"--", "N/A"} or "ACCOUNT TOTAL" in description.upper():
        return None
    if symbol in {"CASH", "FCASH", "SPAXX"} or "CASH" == description.upper():
        return None
    quantity = _money(_value(row, field_map, "quantity"), required=True)
    assert quantity is not None
    market_value = _money(_value(row, field_map, "market_value"))
    mark = _money(_value(row, field_map, "mark"))
    if market_value is None and mark is not None:
        market_value = quantity * mark
    if mark is None and market_value is not None and quantity:
        mark = abs(market_value / quantity)
    average_price = _money(_value(row, field_map, "average_price"))
    cost_basis = _money(_value(row, field_map, "cost_basis"))
    if average_price is None and cost_basis is not None and quantity:
        average_price = abs(cost_basis / quantity)
    option = _option_metadata(symbol=symbol, description=description)
    asset_type = "OPTION" if option is not None else "EQUITY"
    account_mask = _account_mask(_value(row, field_map, "account"))
    # Broker cost-basis sign conventions differ, especially for short options.
    # Only accept an explicitly exported P/L value rather than manufacturing one.
    open_profit_loss = _money(_value(row, field_map, "open_profit_loss"))
    payload: dict[str, object] = {
        "account_mask": account_mask,
        "symbol": option["occ_symbol"] if option else symbol,
        "description": description,
        "asset_type": asset_type,
        "quantity": str(quantity),
        "average_price": _decimal_text(average_price),
        "mark": _decimal_text(mark),
        "market_value": _decimal_text(market_value),
        "day_profit_loss": _decimal_text(_money(_value(row, field_map, "day_profit_loss"))),
        "day_profit_loss_percent": None,
        "strategy": "Short option" if option and quantity is not None and quantity < 0 else None,
        "underlying_symbol": option["underlying_symbol"] if option else None,
        "option_type": option["option_type"] if option else None,
        "expiration_date": option["expiration_date"] if option else None,
        "strike": option["strike"] if option else None,
        "open_profit_loss": _decimal_text(open_profit_loss),
    }
    return ImportRecordKind.POSITION, payload


def _activity_row(
    row: dict[str, str],
    *,
    field_map: dict[str, str],
) -> tuple[ImportRecordKind, dict[str, object]] | None:
    action = _value(row, field_map, "action").upper()
    description = _value(row, field_map, "description")
    if not action and not description:
        return None
    occurred_at = _date_value(_value(row, field_map, "date"))
    symbol = _value(row, field_map, "symbol").strip().upper()
    account_mask = _account_mask(_value(row, field_map, "account"))
    amount = _money(_value(row, field_map, "amount"))
    if "DIVIDEND" in f"{action} {description}":
        return ImportRecordKind.CASH_MOVEMENT, {
            "external_key": "pending",
            "occurred_at": occurred_at.isoformat(),
            "movement_type": "dividend",
            "amount": str(amount or ZERO),
            "description": description or action.title(),
            "account_mask": account_mask,
            "symbol": symbol or None,
            "underlying_symbol": symbol or None,
        }
    lifecycle_type = _lifecycle_type(action, description)
    option = _option_metadata(symbol=symbol, description=description)
    if lifecycle_type is not None and option is not None:
        quantity = abs(_money(_value(row, field_map, "quantity")) or ZERO)
        return ImportRecordKind.LIFECYCLE, {
            "external_key": "pending",
            "occurred_at": occurred_at.isoformat(),
            "event_type": lifecycle_type,
            "option_quantity": str(quantity),
            "stock_quantity": None,
            "cash_amount": _decimal_text(amount),
            "details": {"description": description, "source_action": action},
            "account_mask": account_mask,
            "symbol": option["occ_symbol"],
            "underlying_symbol": option["underlying_symbol"],
            "asset_type": "OPTION",
            "option_type": option["option_type"],
            "expiration_date": option["expiration_date"],
            "strike": option["strike"],
        }
    side = _execution_side(action)
    if side is None:
        if amount is None:
            return None
        return ImportRecordKind.CASH_MOVEMENT, {
            "external_key": "pending",
            "occurred_at": occurred_at.isoformat(),
            "movement_type": "other",
            "amount": str(amount),
            "description": description or action.title(),
            "account_mask": account_mask,
            "symbol": symbol or None,
            "underlying_symbol": option["underlying_symbol"] if option else None,
        }
    parsed_quantity = _money(_value(row, field_map, "quantity"), required=True)
    parsed_price = _money(_value(row, field_map, "price"), required=True)
    assert parsed_quantity is not None
    assert parsed_price is not None
    quantity = abs(parsed_quantity)
    price = abs(parsed_price)
    fees = abs(_money(_value(row, field_map, "fees")) or ZERO)
    multiplier = Decimal("100") if option else Decimal("1")
    gross = quantity * price * multiplier
    net_cash = amount if amount is not None else (gross if side == "sell" else -gross) - fees
    return ImportRecordKind.EXECUTION, {
        "external_key": "pending",
        "order_external_key": None,
        "occurred_at": occurred_at.isoformat(),
        "side": side,
        "position_effect": _position_effect(action),
        "quantity": str(quantity),
        "price": str(price),
        "gross_amount": str(gross),
        "fees": str(fees),
        "net_cash": str(net_cash),
        "account_mask": account_mask,
        "symbol": option["occ_symbol"] if option else symbol,
        "description": description or symbol,
        "asset_type": "OPTION" if option else "EQUITY",
        "underlying_symbol": option["underlying_symbol"] if option else None,
        "option_type": option["option_type"] if option else None,
        "expiration_date": option["expiration_date"] if option else None,
        "strike": option["strike"] if option else None,
        "contract_multiplier": "100" if option else None,
    }


def _option_metadata(*, symbol: str, description: str) -> dict[str, str] | None:
    parsed = parse_occ_option_symbol(symbol)
    if parsed is not None:
        return {
            "occ_symbol": symbol,
            "underlying_symbol": parsed.underlying_symbol,
            "option_type": parsed.option_type,
            "expiration_date": parsed.expiration_date.isoformat(),
            "strike": str(parsed.strike),
        }
    match = _OPTION_DESCRIPTION.search(f"{symbol} {description}".upper())
    if match is None:
        return None
    expiration = _date_value(match.group("date")).date()
    side = "CALL" if match.group("side").upper() in {"C", "CALL"} else "PUT"
    strike = Decimal(match.group("strike"))
    underlying = match.group("underlying").upper()
    occ_symbol = f"{underlying:<6}{expiration:%y%m%d}{side[0]}{int(strike * Decimal('1000')):08d}"
    return {
        "occ_symbol": occ_symbol,
        "underlying_symbol": underlying,
        "option_type": side,
        "expiration_date": expiration.isoformat(),
        "strike": str(strike),
    }


def _header_key(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _value(row: dict[str, str], field_map: dict[str, str], key: str) -> str:
    header = field_map.get(key)
    return row.get(header, "") if header else ""


def _money(value: str, *, required: bool = False) -> Decimal | None:
    cleaned = value.strip().replace("$", "").replace(",", "").replace("%", "")
    if not cleaned or cleaned in {"--", "N/A", "n/a"}:
        if required:
            raise CsvImportError("a required number is blank")
        return None
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()")
    try:
        result = Decimal(cleaned)
    except InvalidOperation as exc:
        raise CsvImportError(f"{value!r} is not a valid number") from exc
    return -result if negative else result


def _date_value(value: str) -> datetime:
    for pattern in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m/%d/%Y %H:%M:%S"):
        try:
            parsed = datetime.strptime(value.strip(), pattern)
            return parsed.replace(tzinfo=UTC)
        except ValueError:
            continue
    raise CsvImportError(f"{value!r} is not a supported date")


def _account_mask(value: str) -> str:
    compact = "".join(character for character in value if character.isalnum())
    return f"...{compact[-4:]}" if compact else "...CSV"


def _execution_side(action: str) -> str | None:
    if any(token in action for token in ("SELL", "SLD", "STO")):
        return "sell"
    if any(token in action for token in ("BUY", "BOT", "BTO", "BTC")):
        return "buy"
    return None


def _position_effect(action: str) -> str:
    if any(token in action for token in ("TO OPEN", "BTO", "STO", "OPENING")):
        return "opening"
    if any(token in action for token in ("TO CLOSE", "BTC", "STC", "CLOSING")):
        return "closing"
    return "unknown"


def _lifecycle_type(action: str, description: str) -> str | None:
    value = f"{action} {description}".upper()
    if "ASSIGN" in value:
        return "assignment"
    if "EXPIR" in value:
        return "expiration"
    if "EXERCISE" in value:
        return "exercise"
    return None


def _decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None
