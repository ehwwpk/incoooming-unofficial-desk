from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from schwab_dashboard.application.values import optional_bool

ZERO = Decimal("0")
STANDARD_CONTRACT_MULTIPLIER = Decimal("100")

_EVENT_TYPES = {
    "assignment": "assignment",
    "assigned": "assignment",
    "exercise": "exercise",
    "exercised": "exercise",
    "expiration": "expiration",
    "expired": "expiration",
}


def lifecycle_event_type(value: object) -> str | None:
    """Return one normalized option-lifecycle type for broker aliases and enums."""

    return _EVENT_TYPES.get(_token(value))


def option_side(value: object) -> str | None:
    """Normalize broker call/put labels without guessing an unknown side."""

    normalized = _token(value)
    if normalized in {"call", "c"}:
        return "call"
    if normalized in {"put", "p"}:
        return "put"
    return None


def contract_multiplier(row: Mapping[str, object]) -> Decimal:
    """Read the broker multiplier, falling back only when neither field exists."""

    raw = row.get("contract_multiplier")
    if raw is None:
        raw = row.get("multiplier")
    return STANDARD_CONTRACT_MULTIPLIER if raw is None else abs(_decimal(raw))


def delivered_share_quantity(row: Mapping[str, object]) -> Decimal:
    """Use delivered shares when supplied, otherwise contracts times multiplier."""

    stock_quantity = abs(_decimal(row.get("stock_quantity")))
    if stock_quantity:
        return stock_quantity
    return abs(_decimal(row.get("option_quantity"))) * contract_multiplier(row)


def delivered_shares(row: Mapping[str, object]) -> Decimal:
    """Return broker-reported delivered shares without truncating adjustments."""

    return delivered_share_quantity(row)


def known_stock_deliverable(row: Mapping[str, object] | None) -> Decimal | None:
    """Return stock units per contract only when the source establishes them."""

    if row is None:
        return None
    deliverable = row.get("deliverable")
    if isinstance(deliverable, Mapping):
        kind = _token(deliverable.get("kind"))
        if kind == "adjusted":
            return None
        if kind == "standard":
            components = deliverable.get("components")
            if isinstance(components, (list, tuple)) and len(components) == 1:
                component = components[0]
                if isinstance(component, Mapping):
                    quantity = _decimal(component.get("quantity"))
                    asset_type = _token(component.get("asset_type"))
                    cash_amount = _decimal(component.get("cash_amount"))
                    symbol = str(component.get("symbol") or "").strip().upper()
                    underlying = str(row.get("underlying_symbol") or "").strip().upper()
                    if (
                        asset_type in {"equity", "etf", "stock"}
                        and quantity > ZERO
                        and cash_amount == ZERO
                        and symbol
                        and (not underlying or symbol == underlying)
                    ):
                        return quantity

    standardness = optional_bool(row.get("is_non_standard"))
    if standardness is True:
        return None
    explicit = _explicit_multiplier(row)
    if standardness is False:
        return explicit or STANDARD_CONTRACT_MULTIPLIER

    signal = f"{row.get('symbol') or ''} {row.get('description') or ''}".upper()
    if any(token in signal for token in ("ADJUSTED", " ADJ ", "NON-STANDARD", "NONSTANDARD")):
        return None
    if _has_conventional_occ_root(str(row.get("symbol") or "")) and (
        explicit is None or explicit == STANDARD_CONTRACT_MULTIPLIER
    ):
        return STANDARD_CONTRACT_MULTIPLIER
    return None


def option_contracts(row: Mapping[str, object]) -> int:
    return int(abs(_decimal(row.get("option_quantity"))))


def _explicit_multiplier(row: Mapping[str, object]) -> Decimal | None:
    raw = row.get("contract_multiplier")
    if raw is None:
        raw = row.get("multiplier")
    if raw is None:
        return None
    value = abs(_decimal(raw))
    return value if value > ZERO else None


def _has_conventional_occ_root(symbol: str) -> bool:
    normalized = symbol.strip().upper()
    if len(normalized) <= 15:
        return False
    root = normalized[:-15].strip()
    tail = normalized[-15:]
    return bool(
        root
        and not any(character.isdigit() for character in root)
        and tail[:6].isdigit()
        and tail[6:7] in {"C", "P"}
        and tail[7:].isdigit()
    )


def _token(value: object) -> str:
    return str(value or "").strip().casefold().split(".")[-1]


def _decimal(value: object) -> Decimal:
    return ZERO if value is None else Decimal(str(value))
