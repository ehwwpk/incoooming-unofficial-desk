from __future__ import annotations

from collections.abc import Sequence

from schwab_dashboard.application.ports.broker import BrokerAccountRecord
from schwab_dashboard.application.ports.tokens import OAuthTokenSet


class MemoryTokenStore:
    def __init__(self, token: OAuthTokenSet | None = None) -> None:
        self.token = token

    def load(self) -> OAuthTokenSet | None:
        return self.token

    def save(self, token: OAuthTokenSet) -> None:
        self.token = token

    def delete(self) -> None:
        self.token = None


class FakeBrokerGateway:
    def __init__(self, records: Sequence[BrokerAccountRecord]) -> None:
        self.records = records
        self.calls = 0

    def fetch_accounts_with_positions(self) -> Sequence[BrokerAccountRecord]:
        self.calls += 1
        return self.records
