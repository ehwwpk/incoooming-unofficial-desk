from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from schwab_dashboard.domain.broker import BrokerAccount, BrokerPosition


@dataclass(frozen=True, slots=True)
class BrokerAccountRecord:
    account: BrokerAccount
    positions: tuple[BrokerPosition, ...]
    raw_payload: Mapping[str, Any]


class BrokerGateway(Protocol):
    def fetch_accounts_with_positions(self) -> Sequence[BrokerAccountRecord]: ...
