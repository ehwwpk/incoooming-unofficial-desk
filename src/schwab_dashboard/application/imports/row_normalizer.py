from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from schwab_dashboard.application.imports.csv_text import header_key
from schwab_dashboard.application.imports.errors import CsvImportError
from schwab_dashboard.application.imports.option_normalizer import (
    contract_multiplier,
    option_metadata,
)
from schwab_dashboard.domain.data_source import BrokerKind, ImportRecordKind

ZERO = Decimal("0")

_ALIASES = {
    "account": ("account", "accountnumber", "accountname", "accountnamenumber"),
    "symbol": ("symbol", "instrument", "securitysymbol", "ticker"),
    "description": ("description", "securitydescription", "name", "instrumentdescription"),
    "quantity": ("quantity", "qty", "shares", "position", "filled", "totalqty"),
    "mark": ("lastprice", "price", "currentprice", "mark", "last"),
    "market_value": ("marketvalue", "currentvalue", "positiondollarvalue", "value"),
    "average_price": ("averageprice", "averagecostbasis", "costshare", "costpershare"),
    "cost_basis": ("costbasis", "costtotal", "totalcostbasis"),
    "day_profit_loss": ("daychangepl", "daychange", "todaysgainlossdollar", "daygainloss"),
    "open_profit_loss": (
        "totalgainlossdollar",
        "totalgainloss",
        "openprofitloss",
        "unrealizedgainloss",
    ),
    "date": ("date", "activitydate", "rundate", "tradedate", "processdate", "filledtime"),
    "action": ("action", "transcode", "transactiontype", "type", "side"),
    "price": ("price", "priceamount", "tradeprice", "avgprice"),
    "fees": ("feescomm", "fees", "commission", "commissionfees", "commfee"),
    "amount": ("amount", "netamount", "cashamount", "proceeds"),
    "status": ("status", "orderstatus"),
    "multiplier": ("multiplier", "contractmultiplier", "mult"),
}


def field_map(headers: tuple[str, ...]) -> dict[str, str]:
    normalized = {header_key(header): header for header in headers}
    return {
        canonical: match
        for canonical, aliases in _ALIASES.items()
        if (
            match := next(
                (normalized[key] for alias in aliases if (key := header_key(alias)) in normalized),
                None,
            )
        )
    }


def detect_file_kind(mapped_fields: dict[str, str]) -> str:
    if {"date", "action"} <= mapped_fields.keys() and (
        "amount" in mapped_fields or {"quantity", "price"} <= mapped_fields.keys()
    ):
        return "activity"
    if {"symbol", "quantity"} <= mapped_fields.keys() and (
        "market_value" in mapped_fields or "mark" in mapped_fields
    ):
        return "positions"
    raise CsvImportError("The detected header is missing required position or activity columns.")


def normalize_position_row(
    row: dict[str, str], *, mapped_fields: dict[str, str]
) -> tuple[ImportRecordKind, dict[str, object]] | None:
    symbol = _value(row, mapped_fields, "symbol").strip().upper()
    description = _value(row, mapped_fields, "description") or symbol
    if not symbol or symbol in {"--", "N/A"}:
        return None
    if symbol in {"CASH", "FCASH", "SPAXX"} or description.strip().upper() == "CASH":
        return None
    quantity = _money(_value(row, mapped_fields, "quantity"), required=True)
    assert quantity is not None
    market_value = _money(_value(row, mapped_fields, "market_value"))
    mark = _money(_value(row, mapped_fields, "mark"))
    if market_value is None and mark is not None:
        market_value = quantity * mark
    if mark is None and market_value is not None and quantity:
        mark = abs(market_value / quantity)
    average_price = _money(_value(row, mapped_fields, "average_price"))
    cost_basis = _money(_value(row, mapped_fields, "cost_basis"))
    if average_price is None and cost_basis is not None and quantity:
        average_price = abs(cost_basis / quantity)
    option = option_metadata(symbol=symbol, description=description)
    explicit_multiplier = _money(_value(row, mapped_fields, "multiplier"))
    multiplier, multiplier_source = contract_multiplier(
        explicit=explicit_multiplier,
        symbol=symbol,
        description=description,
        is_option=option is not None,
    )
    if option and multiplier is None:
        return ImportRecordKind.POSITION, {
            "_needs_review": True,
            "_review_reason": (
                "Adjusted option position has no exported multiplier; "
                "coverage and market value would be unsafe to infer."
            ),
        }
    return ImportRecordKind.POSITION, {
        "account_mask": _account_mask(_value(row, mapped_fields, "account")),
        "symbol": option["occ_symbol"] if option else symbol,
        "description": description,
        "asset_type": "OPTION" if option else "EQUITY",
        "quantity": str(quantity),
        "average_price": _decimal_text(average_price),
        "mark": _decimal_text(mark),
        "market_value": _decimal_text(market_value),
        "day_profit_loss": _decimal_text(_money(_value(row, mapped_fields, "day_profit_loss"))),
        "day_profit_loss_percent": None,
        "strategy": "Short option" if option and quantity < 0 else None,
        "underlying_symbol": option["underlying_symbol"] if option else None,
        "option_type": option["option_type"] if option else None,
        "expiration_date": option["expiration_date"] if option else None,
        "strike": option["strike"] if option else None,
        "open_profit_loss": _decimal_text(_money(_value(row, mapped_fields, "open_profit_loss"))),
        "contract_multiplier": _decimal_text(multiplier),
        "multiplier_source": multiplier_source,
    }


def normalize_activity_row(
    row: dict[str, str], *, mapped_fields: dict[str, str], broker: BrokerKind
) -> tuple[ImportRecordKind, dict[str, object]] | None:
    action = _value(row, mapped_fields, "action").upper()
    description = _value(row, mapped_fields, "description")
    status = _value(row, mapped_fields, "status").upper()
    if broker is BrokerKind.WEBULL and status and status != "FILLED":
        return None
    if not action and not description:
        return None
    occurred_at = _date_value(_value(row, mapped_fields, "date"))
    symbol = _value(row, mapped_fields, "symbol").strip().upper()
    account_mask = _account_mask(_value(row, mapped_fields, "account"))
    amount = _money(_value(row, mapped_fields, "amount"))
    classification = _cash_type(action, description)
    if classification is not None:
        if amount is None:
            raise CsvImportError(f"{classification.replace('_', ' ')} amount is blank")
        return ImportRecordKind.CASH_MOVEMENT, {
            "external_key": "pending",
            "occurred_at": occurred_at.isoformat(),
            "movement_type": classification,
            "amount": str(amount),
            "description": description or action.title(),
            "account_mask": account_mask,
            "symbol": symbol or None,
            "underlying_symbol": symbol or None,
        }
    option = option_metadata(symbol=symbol, description=description)
    lifecycle_type = _lifecycle_type(action, description)
    if lifecycle_type is not None:
        if option is None:
            raise CsvImportError("option lifecycle row has no recognizable contract")
        quantity = abs(_money(_value(row, mapped_fields, "quantity")) or ZERO)
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
            "_needs_review": True,
            "_review_reason": (
                f"Unknown cash action {action or description!r}; classify it before import."
            ),
        }
    quantity = abs(_money(_value(row, mapped_fields, "quantity"), required=True) or ZERO)
    price = abs(_money(_value(row, mapped_fields, "price"), required=True) or ZERO)
    fees = abs(_money(_value(row, mapped_fields, "fees")) or ZERO)
    explicit_multiplier = _money(_value(row, mapped_fields, "multiplier"))
    multiplier, multiplier_source = contract_multiplier(
        explicit=explicit_multiplier,
        symbol=symbol,
        description=description,
        is_option=option is not None,
    )
    if option and multiplier is None and amount is None:
        return ImportRecordKind.EXECUTION, {
            "_needs_review": True,
            "_review_reason": (
                "Adjusted option has no exported multiplier or net amount; 100x was not assumed."
            ),
        }
    gross = (
        quantity * price * (multiplier or Decimal("1"))
        if not option or multiplier is not None
        else max(ZERO, abs(amount or ZERO) - fees)
    )
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
        "contract_multiplier": _decimal_text(multiplier),
        "multiplier_source": multiplier_source,
    }


def is_summary_row(row: dict[str, str]) -> bool:
    text = " ".join(row.values()).upper()
    return any(
        token in text
        for token in ("ACCOUNT TOTAL", "TOTAL ACCOUNT VALUE", "THE DATA AND INFORMATION")
    )


def _cash_type(action: str, description: str) -> str | None:
    value = f"{action} {description}".upper()
    if any(token in value for token in ("DIVIDEND", "QUAL DIV", "NON-QUAL DIV", "CDIV")):
        return "dividend"
    if any(
        token in value for token in ("ACH", "WIRE", "TRANSFER", "DEPOSIT", "WITHDRAWAL", "JOURNAL")
    ):
        return "transfer"
    if "INTEREST" in value:
        return "interest"
    if any(token in value for token in ("WITHHOLD", "FOREIGN TAX", "TAX WITHHELD")):
        return "withholding"
    if any(token in value for token in ("FEE", "COMMISSION")) and not _execution_side(action):
        return "fee"
    return None


def _execution_side(action: str) -> str | None:
    if any(token in action for token in ("SELL", "SLD", "STO", "STC")):
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


def _date_value(value: str) -> datetime:
    clean = value.strip().replace("T", " ").removesuffix("Z")
    for pattern in (
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %I:%M:%S %p",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(clean, pattern).replace(tzinfo=UTC)
        except ValueError:
            pass
    raise CsvImportError(f"{value!r} is not a supported date")


def _money(value: str, *, required: bool = False) -> Decimal | None:
    cleaned = value.strip().replace("$", "").replace(",", "").replace("%", "")
    if not cleaned or cleaned.upper() in {"--", "N/A", "NA"}:
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


def _value(row: dict[str, str], mapped_fields: dict[str, str], key: str) -> str:
    return row.get(mapped_fields.get(key, ""), "")


def _account_mask(value: str) -> str:
    compact = "".join(character for character in value if character.isalnum())
    return f"...{compact[-4:]}" if compact else "...CSV"


def _decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None
