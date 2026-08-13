from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi.templating import Jinja2Templates

from schwab_dashboard.application.dashboard.anchors import option_contract_anchor
from schwab_dashboard.application.market_time import market_date

WEB_ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=WEB_ROOT / "templates")


def money(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "—"
    amount = Decimal(str(value))
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.{decimals}f}"


def number(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "—"
    amount = Decimal(str(value))
    return f"{amount:,.{decimals}f}"


def percent(value: Any, decimals: int = 1) -> str:
    if value is None:
        return "—"
    amount = Decimal(str(value))
    return f"{amount:,.{decimals}f}%"


def short_date(value: date | datetime | None) -> str:
    if value is None:
        return "Not available"
    display_date = market_date(value) if isinstance(value, datetime) else value
    return display_date.strftime("%b %d, %Y")


def pnl_class(value: Any) -> str:
    if value is None:
        return "muted"
    amount = Decimal(str(value))
    if amount > 0:
        return "positive"
    if amount < 0:
        return "negative"
    return "muted"


templates.env.filters.update(
    {
        "money": money,
        "number": number,
        "percent": percent,
        "short_date": short_date,
        "pnl_class": pnl_class,
    }
)
templates.env.filters["option_anchor"] = option_contract_anchor
