from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from schwab_dashboard.domain.validation import (
    require_aware,
    require_non_negative,
    require_optional_non_negative,
    require_text,
)


class AssetType(StrEnum):
    EQUITY = "equity"
    ETF = "etf"
    OPTION = "option"
    CASH = "cash"
    MUTUAL_FUND = "mutual_fund"
    FIXED_INCOME = "fixed_income"
    UNKNOWN = "unknown"


class OptionSide(StrEnum):
    CALL = "call"
    PUT = "put"


class DeliverableKind(StrEnum):
    STANDARD = "standard"
    ADJUSTED = "adjusted"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class DeliverableComponent:
    asset_type: AssetType
    quantity: Decimal
    symbol: str | None = None
    cash_amount: Decimal | None = None
    currency: str | None = None

    def __post_init__(self) -> None:
        require_non_negative(self.quantity, "quantity")
        require_optional_non_negative(self.cash_amount, "cash_amount")
        if self.symbol is not None:
            require_text(self.symbol, "symbol")
        if self.currency is not None:
            require_text(self.currency, "currency")


@dataclass(frozen=True, slots=True)
class OptionDeliverable:
    kind: DeliverableKind
    components: tuple[DeliverableComponent, ...]
    description: str | None = None

    def __post_init__(self) -> None:
        if self.description is not None:
            require_text(self.description, "description")
        if self.kind is not DeliverableKind.UNKNOWN and not self.components:
            raise ValueError("a known option deliverable must have at least one component")


@dataclass(frozen=True, slots=True)
class InstrumentRecord:
    source: str
    external_key: str
    symbol: str
    asset_type: AssetType
    observed_at: datetime
    description: str | None = None
    underlying_symbol: str | None = None
    option_side: OptionSide | None = None
    expiration_date: date | None = None
    strike: Decimal | None = None
    contract_multiplier: Decimal | None = None
    deliverable: OptionDeliverable | None = None

    def __post_init__(self) -> None:
        require_text(self.source, "source")
        require_text(self.external_key, "external_key")
        require_text(self.symbol, "symbol")
        require_aware(self.observed_at, "observed_at")
        require_optional_non_negative(self.strike, "strike")
        require_optional_non_negative(self.contract_multiplier, "contract_multiplier")
        if self.description is not None:
            require_text(self.description, "description")
        if self.underlying_symbol is not None:
            require_text(self.underlying_symbol, "underlying_symbol")
        if self.asset_type is not AssetType.OPTION:
            option_fields = (
                self.option_side,
                self.expiration_date,
                self.strike,
                self.contract_multiplier,
                self.deliverable,
            )
            if any(value is not None for value in option_fields):
                raise ValueError("option metadata is only valid for option instruments")
