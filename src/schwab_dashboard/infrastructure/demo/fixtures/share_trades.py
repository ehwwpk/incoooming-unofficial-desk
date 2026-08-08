"""Sparse simulated share transactions for the demo price tape.

These events demonstrate the secondary chart layer without pretending to be a
complete tax-lot ledger. Assigned shares remain represented by the option
lifecycle's assignment event instead of being duplicated here.
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
    "KTOS": (ShareTradeFixture("KTOS", date(2026, 6, 24), "buy", 100, D("47.95")),),
    "URNM": (ShareTradeFixture("URNM", date(2026, 7, 17), "buy", 100, D("48.22")),),
}
