from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from schwab_dashboard.application.imports.csv_text import decimal_cell, header_key
from schwab_dashboard.application.imports.errors import CsvImportError
from schwab_dashboard.application.imports.option_normalizer import (
    contract_multiplier,
    looks_like_option,
    option_metadata,
)
from schwab_dashboard.application.market_time import MARKET_TIME_ZONE
from schwab_dashboard.domain.data_source import BrokerKind, ImportRecordKind

ZERO = Decimal("0")

_ALIASES = {
    "account": ("accountnumber", "accountnamenumber", "account", "accountname"),
    "symbol": ("symbol", "instrument", "securitysymbol", "ticker"),
    "description": ("description", "securitydescription", "name", "instrumentdescription"),
    "quantity": ("quantity", "qty", "shares", "position", "filled", "totalqty"),
    "stock_quantity": ("stockquantity", "deliveredshares", "sharesdelivered"),
    "mark": (
        "lastprice",
        "lastpricedollar",
        "price",
        "pricedollar",
        "currentprice",
        "currentpricedollar",
        "mostrecentprice",
        "mostrecentpricedollar",
        "mark",
        "markdollar",
        "last",
    ),
    "market_value": (
        "marketvalue",
        "marketvaluedollar",
        "currentvalue",
        "currentvaluedollar",
        "mostrecentvalue",
        "mostrecentvaluedollar",
        "positiondollarvalue",
        "value",
    ),
    "average_price": (
        "averageprice",
        "averagepricedollar",
        "averagecostbasis",
        "costbasispershare",
        "costbasispersharedollar",
        "costshare",
        "costpershare",
        "costpersharedollar",
    ),
    "cost_basis": (
        "costbasis",
        "costbasisdollar",
        "costtotal",
        "totalcostbasis",
        "totalcostbasisdollar",
    ),
    "day_profit_loss": (
        "daychangepl",
        "daychangepldollar",
        "daychangedollar",
        "todaysgainlossdollar",
        "daygainlossdollar",
    ),
    "open_profit_loss": (
        "totalgainlossdollar",
        "openprofitloss",
        "openprofitlossdollar",
        "unrealizedgainloss",
        "unrealizedgainlossdollar",
        "changesincepurchasedollar",
        "pldollar",
    ),
    "date": ("date", "activitydate", "rundate", "tradedate", "processdate", "filledtime"),
    "action": ("action", "transcode", "transactiontype", "type", "side"),
    "price": (
        "price",
        "pricedollar",
        "priceamount",
        "tradeprice",
        "tradepricedollar",
        "avgprice",
        "avgpricedollar",
    ),
    "fees": (
        "feescomm",
        "fees",
        "feesdollar",
        "commission",
        "commissiondollar",
        "commissionfees",
        "commfee",
    ),
    "amount": (
        "amount",
        "amountdollar",
        "netamount",
        "netamountdollar",
        "cashamount",
        "cashamountdollar",
        "proceeds",
        "proceedsdollar",
    ),
    "status": ("status", "orderstatus"),
    "multiplier": ("multiplier", "contractmultiplier", "mult"),
}


def field_map(headers: tuple[str, ...], *, broker: BrokerKind | None = None) -> dict[str, str]:
    normalized = {header_key(header): header for header in headers}
    aliases_by_field = dict(_ALIASES)
    if broker is BrokerKind.WEBULL:
        aliases_by_field["quantity"] = (
            "filled",
            *(alias for alias in _ALIASES["quantity"] if alias != "filled"),
        )
    return {
        canonical: match
        for canonical, aliases in aliases_by_field.items()
        if (
            match := next(
                (normalized[key] for alias in aliases if (key := header_key(alias)) in normalized),
                None,
            )
        )
    }


def validate_field_aliases(headers: tuple[str, ...], *, broker: BrokerKind) -> None:
    """Reject two source columns that claim the same normalized ledger field."""

    permitted_precedence = {
        BrokerKind.ROBINHOOD: {"date"},
        BrokerKind.WEBULL: {"quantity"},
        BrokerKind.FIDELITY: {"account"},
    }
    normalized_headers = tuple((header_key(header), header) for header in headers if header)
    conflicts: list[str] = []
    for canonical, aliases in _ALIASES.items():
        if canonical in permitted_precedence.get(broker, set()):
            continue
        alias_keys = {header_key(alias) for alias in aliases}
        matches = [header for key, header in normalized_headers if key in alias_keys]
        if len(matches) > 1:
            conflicts.append(f"{canonical}: {', '.join(matches)}")
    if conflicts:
        raise CsvImportError(
            "The CSV header has ambiguous aliases for one field: " + "; ".join(conflicts) + "."
        )


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
    if quantity == ZERO:
        return None
    option = option_metadata(symbol=symbol, description=description)
    if option is None and looks_like_option(symbol=symbol, description=description):
        return ImportRecordKind.POSITION, {
            "_needs_review": True,
            "_review_reason": "Option position has no safely recognized contract identity.",
        }
    if option is not None and quantity != quantity.to_integral_value():
        return ImportRecordKind.POSITION, {
            "_needs_review": True,
            "_review_reason": "Option position quantity is not a whole contract count.",
        }
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
                "Option position has no reliable exported multiplier; "
                "coverage and market value would be unsafe to infer."
            ),
        }
    value_scale = multiplier if option else Decimal("1")
    assert value_scale is not None
    market_value = _money(_value(row, mapped_fields, "market_value"))
    parsed_mark = _money(_value(row, mapped_fields, "mark"))
    mark = abs(parsed_mark) if parsed_mark is not None else None
    if market_value is None and mark is not None:
        market_value = quantity * mark * value_scale
    elif market_value is not None:
        market_value = abs(market_value) if quantity > ZERO else -abs(market_value)
    if mark is None and market_value is not None and quantity:
        mark = abs(market_value / (quantity * value_scale))
    parsed_average_price = _money(_value(row, mapped_fields, "average_price"))
    average_price = abs(parsed_average_price) if parsed_average_price is not None else None
    cost_basis = _money(_value(row, mapped_fields, "cost_basis"))
    if average_price is None and cost_basis is not None and quantity:
        average_price = abs(cost_basis / (quantity * value_scale))
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
    if broker is BrokerKind.WEBULL:
        filled_quantity = _money(_value(row, mapped_fields, "quantity"))
        if filled_quantity is None or filled_quantity == ZERO:
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
            "amount": str(
                _directional_cash_movement(
                    amount,
                    classification=classification,
                    action=action,
                    description=description,
                )
            ),
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
        stock_quantity = abs(_money(_value(row, mapped_fields, "stock_quantity")) or ZERO)
        if quantity == ZERO and stock_quantity == ZERO:
            return ImportRecordKind.LIFECYCLE, {
                "_needs_review": True,
                "_review_reason": (
                    "Option lifecycle contract and delivered-share quantities are blank or zero."
                ),
            }
        explicit_multiplier = _money(_value(row, mapped_fields, "multiplier"))
        multiplier, multiplier_source = contract_multiplier(
            explicit=explicit_multiplier,
            symbol=symbol,
            description=description,
            is_option=True,
        )
        if quantity != quantity.to_integral_value():
            return ImportRecordKind.LIFECYCLE, {
                "_needs_review": True,
                "_review_reason": "Option lifecycle quantity is not a whole contract count.",
            }
        if quantity == ZERO and stock_quantity > ZERO:
            if multiplier is None:
                return ImportRecordKind.LIFECYCLE, {
                    "_needs_review": True,
                    "_review_reason": (
                        "Option lifecycle row has delivered shares but no contract count "
                        "or multiplier."
                    ),
                }
            derived_quantity = stock_quantity / multiplier
            if derived_quantity != derived_quantity.to_integral_value():
                return ImportRecordKind.LIFECYCLE, {
                    "_needs_review": True,
                    "_review_reason": (
                        "Delivered shares do not divide into a whole contract count."
                    ),
                }
            quantity = derived_quantity
        if multiplier is None and stock_quantity == ZERO:
            return ImportRecordKind.LIFECYCLE, {
                "_needs_review": True,
                "_review_reason": (
                    "Adjusted option lifecycle row has no exported multiplier or delivered shares."
                ),
            }
        return ImportRecordKind.LIFECYCLE, {
            "external_key": "pending",
            "occurred_at": occurred_at.isoformat(),
            "event_type": lifecycle_type,
            "option_quantity": str(quantity),
            "stock_quantity": str(stock_quantity) if stock_quantity else None,
            "cash_amount": _decimal_text(amount),
            "details": {"description": description, "source_action": action},
            "account_mask": account_mask,
            "symbol": option["occ_symbol"],
            "underlying_symbol": option["underlying_symbol"],
            "asset_type": "OPTION",
            "option_type": option["option_type"],
            "expiration_date": option["expiration_date"],
            "strike": option["strike"],
            "contract_multiplier": _decimal_text(multiplier),
            "multiplier_source": multiplier_source,
        }
    side = _execution_side(action)
    if side is None:
        if amount is None:
            return None
        # Preserve unexplained cash so return reconstruction can fail closed.
        # Dropping the row would let an unknown deposit look like investment
        # performance in an otherwise usable imported book.
        return ImportRecordKind.CASH_MOVEMENT, {
            "external_key": "pending",
            "occurred_at": occurred_at.isoformat(),
            "movement_type": "other",
            "amount": str(amount),
            "description": description or action or "Unclassified cash activity",
            "account_mask": account_mask,
            "symbol": symbol or None,
            "underlying_symbol": symbol or None,
        }
    if not symbol:
        raise CsvImportError("execution symbol is blank")
    if option is None and looks_like_option(symbol=symbol, description=description):
        return ImportRecordKind.EXECUTION, {
            "_needs_review": True,
            "_review_reason": "Option execution has no safely recognized contract identity.",
        }
    quantity = abs(_money(_value(row, mapped_fields, "quantity"), required=True) or ZERO)
    price = abs(_money(_value(row, mapped_fields, "price"), required=True) or ZERO)
    if quantity == ZERO:
        raise CsvImportError("execution quantity must be greater than zero")
    if option is not None and quantity != quantity.to_integral_value():
        return ImportRecordKind.EXECUTION, {
            "_needs_review": True,
            "_review_reason": "Option execution quantity is not a whole contract count.",
        }
    if price == ZERO and amount is None:
        raise CsvImportError("zero-price execution has no exported net amount")
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
        else _gross_from_net(amount or ZERO, side=side, fees=fees)
    )
    net_cash = (
        _directional_net_cash(amount, side=side)
        if amount is not None
        else (gross if side == "sell" else -gross) - fees
    )
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
    # An explicit trade action wins over words in a security's name, such as
    # "Dividend Equity ETF" or "Interest Rate Hedge ETF".
    if _execution_side(action) is not None:
        return None
    value = f"{action} {description}".upper()
    if _has_phrase(
        value,
        "WITHHOLD",
        "WITHHOLDING",
        "WITHHELD",
        "FOREIGN TAX",
        "TAX WITHHELD",
    ):
        return "withholding"
    if _has_phrase(value, "FEE", "FEES", "COMMISSION", "COMMISSIONS") and not _execution_side(
        action
    ):
        return "fee"
    if _has_phrase(value, "INTEREST"):
        return "interest"
    if _has_phrase(
        value,
        "DIVIDEND",
        "DIVIDENDS",
        "QUAL DIV",
        "NON-QUAL DIV",
        "CDIV",
    ):
        return "dividend"
    if _has_phrase(
        value,
        "ACH",
        "WIRE",
        "DEPOSIT",
        "WITHDRAWAL",
        "CASH RECEIPT",
        "CASH DISBURSEMENT",
    ):
        return "transfer"
    if _has_phrase(value, "JOURNAL", "TRANSFER", "TRANSFERRED"):
        # A bare journal/transfer can be an internal balance move, corporate
        # action, or owner funding.  Keep it visible as unresolved cash rather
        # than choosing a side of the performance boundary.
        return "other"
    return None


def _gross_from_net(amount: Decimal, *, side: str, fees: Decimal) -> Decimal:
    """Recover pre-fee cash when an adjusted contract has no multiplier."""

    if side == "sell":
        return max(ZERO, amount + fees) if amount < ZERO else amount + fees
    return max(ZERO, abs(amount) - fees)


def _directional_net_cash(
    amount: Decimal,
    *,
    side: str,
) -> Decimal:
    """Apply trade direction when an export prints unsigned cash amounts."""

    magnitude = abs(amount)
    if side == "buy":
        return -magnitude
    return amount if amount < ZERO else magnitude


def _directional_cash_movement(
    amount: Decimal,
    *,
    classification: str,
    action: str,
    description: str,
) -> Decimal:
    """Normalize only movements whose language establishes cash direction."""

    if classification in {"fee", "withholding"}:
        return -abs(amount)
    if classification != "transfer":
        return amount
    value = f"{action} {description}".upper()
    if _has_phrase(
        value,
        "WITHDRAWAL",
        "WITHDRAWN",
        "DISBURSEMENT",
        "DISBURSED",
        "WIRE OUT",
        "OUTBOUND",
    ):
        return -abs(amount)
    if _has_phrase(value, "DEPOSIT", "DEPOSITED", "RECEIPT", "WIRE IN", "INBOUND"):
        return abs(amount)
    return amount


def _execution_side(action: str) -> str | None:
    if _has_phrase(action, "SELL", "SOLD", "SLD", "STO", "STC"):
        return "sell"
    if _has_phrase(action, "BUY", "BOUGHT", "BOT", "BTO", "BTC"):
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
    if _has_phrase(value, "ASSIGN", "ASSIGNED", "ASSIGNMENT"):
        return "assignment"
    if _has_phrase(value, "EXPIRE", "EXPIRED", "EXPIRATION"):
        return "expiration"
    if _has_phrase(value, "EXERCISE", "EXERCISED"):
        return "exercise"
    return None


def _has_phrase(value: str, *phrases: str) -> bool:
    return any(
        re.search(rf"(?<![A-Z0-9]){re.escape(phrase)}(?![A-Z0-9])", value) is not None
        for phrase in phrases
    )


def _date_value(value: str) -> datetime:
    raw = value.strip()
    try:
        parsed_iso = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        pass
    else:
        return (
            parsed_iso
            if parsed_iso.tzinfo is not None
            else parsed_iso.replace(tzinfo=MARKET_TIME_ZONE)
        )
    clean = raw.replace("T", " ")
    for pattern in (
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %I:%M:%S %p",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            # Broker CSV timestamps without an offset are calendar facts, not
            # UTC instants. Preserve their displayed U.S. market date so a
            # midnight execution or dividend cannot slide to the prior day.
            return datetime.strptime(clean, pattern).replace(tzinfo=MARKET_TIME_ZONE)
        except ValueError:
            pass
    raise CsvImportError(f"{value!r} is not a supported date")


def _money(value: str, *, required: bool = False) -> Decimal | None:
    return decimal_cell(value, required=required)


def _value(row: dict[str, str], mapped_fields: dict[str, str], key: str) -> str:
    return row.get(mapped_fields.get(key, ""), "")


def _account_mask(value: str) -> str:
    compact = "".join(character for character in value if character.isalnum())
    return f"...{compact[-4:]}" if any(character.isdigit() for character in compact) else "...CSV"


def _decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None
