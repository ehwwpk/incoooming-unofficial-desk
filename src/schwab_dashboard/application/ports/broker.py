from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from schwab_dashboard.domain.broker import (
    BrokerAccount,
    BrokerAccountBalances,
    BrokerPosition,
)


@dataclass(frozen=True, slots=True)
class BrokerAccountRecord:
    account: BrokerAccount
    positions: tuple[BrokerPosition, ...]
    raw_payload: Mapping[str, Any]
    balances: BrokerAccountBalances | None = None


class BrokerGateway(Protocol):
    def fetch_accounts_with_positions(self) -> Sequence[BrokerAccountRecord]: ...
