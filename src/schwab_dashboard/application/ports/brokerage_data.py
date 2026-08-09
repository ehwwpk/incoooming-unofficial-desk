from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from schwab_dashboard.application.ports.broker import BrokerAccountRecord


class DataSourceKind(StrEnum):
    DIRECT_BROKER = "direct_broker"
    AGGREGATOR = "aggregator"
    FILE_IMPORT = "file_import"


class BrokerCapability(StrEnum):
    ACCOUNTS = "accounts"
    BALANCES = "balances"
    POSITIONS = "positions"
    ACTIVITIES = "activities"
    EXECUTIONS = "executions"
    OPTION_CONTRACTS = "option_contracts"
    TAX_LOTS = "tax_lots"
    OPEN_ORDERS = "open_orders"
    MARKET_QUOTES = "market_quotes"


class CapabilityState(StrEnum):
    AVAILABLE = "available"
    CONDITIONAL = "conditional"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class RefreshClass(StrEnum):
    REAL_TIME = "real_time"
    DELAYED = "delayed"
    DAILY = "daily"
    FILE_SNAPSHOT = "file_snapshot"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CapabilitySupport:
    capability: BrokerCapability
    state: CapabilityState
    refresh: RefreshClass
    note: str


@dataclass(frozen=True, slots=True)
class BrokerageSourceProfile:
    source_key: str
    display_name: str
    kind: DataSourceKind
    read_only: bool
    support: tuple[CapabilitySupport, ...]

    def __post_init__(self) -> None:
        if not self.source_key.strip() or not self.display_name.strip():
            raise ValueError("source identity must not be blank")
        if not self.read_only:
            raise ValueError("analytics brokerage sources must be read-only")
        capabilities = [item.capability for item in self.support]
        if len(set(capabilities)) != len(capabilities):
            raise ValueError("capabilities must not be duplicated")

    def capability(self, key: BrokerCapability) -> CapabilitySupport:
        return next(
            (item for item in self.support if item.capability is key),
            CapabilitySupport(
                capability=key,
                state=CapabilityState.UNKNOWN,
                refresh=RefreshClass.UNKNOWN,
                note="Adapter has not declared this capability.",
            ),
        )


class BrokerageDataAdapter(Protocol):
    """Read-only source boundary; adapters normalize into canonical records."""

    @property
    def profile(self) -> BrokerageSourceProfile: ...

    def fetch_accounts_with_positions(self) -> Sequence[BrokerAccountRecord]: ...

    def fetch_activity_payloads(self) -> Sequence[Mapping[str, Any]]: ...
