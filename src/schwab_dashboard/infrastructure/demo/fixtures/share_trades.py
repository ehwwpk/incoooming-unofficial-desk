"""Simulated share transactions shared by the demo tape and account replay.

Supplemental KTOS and URNM round trips keep every historical call covered while
preserving the final displayed holdings. Assigned shares remain represented by
the option lifecycle instead of being duplicated here. This is fictional
inventory history, not a tax-lot ledger or a trading recommendation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

D = Decimal


@dataclass(frozen=True, slots=True)
class ShareTradeFixture:
    symbol: str
    traded_on: date
    action: str
    shares: int
    price: Decimal


SHARE_TRADES: Mapping[str, Sequence[ShareTradeFixture]] = {
    "CVX": (
        ShareTradeFixture("CVX", date(2026, 6, 24), "buy", 100, D("171.45")),
        ShareTradeFixture("CVX", date(2026, 7, 23), "sell", 100, D("194.42")),
    ),
    "KTOS": (
        ShareTradeFixture("KTOS", date(2026, 6, 24), "buy", 100, D("47.95")),
        ShareTradeFixture("KTOS", date(2026, 6, 26), "buy", 100, D("47.21")),
        ShareTradeFixture("KTOS", date(2026, 7, 10), "sell", 100, D("48.19")),
    ),
    "URNM": (
        ShareTradeFixture("URNM", date(2026, 6, 5), "buy", 400, D("55.28")),
        ShareTradeFixture("URNM", date(2026, 7, 17), "sell", 400, D("48.22")),
        ShareTradeFixture("URNM", date(2026, 7, 17), "buy", 100, D("48.22")),
    ),
}
