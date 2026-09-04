from __future__ import annotations

from collections.abc import Mapping


def is_option_execution(row: Mapping[str, object]) -> bool:
    return _token(row.get("asset_type")) == "option"


def is_opening_sale(row: Mapping[str, object]) -> bool:
    return _token(row.get("side")) in {"sell", "sold"} and _token(row.get("position_effect")) in {
        "open",
        "opening",
    }


def is_closing_buy(row: Mapping[str, object]) -> bool:
    return _token(row.get("side")) in {"buy", "bought"} and _token(row.get("position_effect")) in {
        "close",
        "closing",
    }


def is_short_premium_execution(row: Mapping[str, object]) -> bool:
    """True for short-premium STO and BTC. Calls and puts. Not equity. Not STC."""

    return is_option_execution(row) and (is_opening_sale(row) or is_closing_buy(row))


def option_cash_action_label(row: Mapping[str, object]) -> str:
    side = _token(row.get("option_side"))
    kind = "PUT" if side in {"put", "p"} else "CALL" if side in {"call", "c"} else "OPTION"
    return f"{kind} SOLD" if is_opening_sale(row) else f"{kind} CLOSED"


def _token(value: object) -> str:
    return str(value or "").strip().casefold().split(".")[-1]
