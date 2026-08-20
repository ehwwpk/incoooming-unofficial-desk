from __future__ import annotations

from collections.abc import Mapping


def is_opening_sale(row: Mapping[str, object]) -> bool:
    return str(row.get("side")) == "sell" and str(row.get("position_effect")) == "opening"


def is_closing_buy(row: Mapping[str, object]) -> bool:
    return str(row.get("side")) == "buy" and str(row.get("position_effect")) == "closing"


def is_short_premium_execution(row: Mapping[str, object]) -> bool:
    """True for short-premium STO and BTC. Calls and puts. Not equity. Not STC."""

    return str(row.get("asset_type") or "").lower() == "option" and (
        is_opening_sale(row) or is_closing_buy(row)
    )


def option_cash_action_label(row: Mapping[str, object]) -> str:
    side = str(row.get("option_side") or "").strip().lower()
    kind = "PUT" if side == "put" else "CALL"
    return f"{kind} SOLD" if is_opening_sale(row) else f"{kind} CLOSED"
