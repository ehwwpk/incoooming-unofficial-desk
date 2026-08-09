from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from schwab_dashboard.domain.instruments import InstrumentRecord
from schwab_dashboard.domain.validation import (
    require_aware,
    require_non_negative,
    require_optional_non_negative,
    require_text,
)


class ExecutionSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class PositionEffect(StrEnum):
    OPENING = "opening"
    CLOSING = "closing"
    UNKNOWN = "unknown"


class CashMovementType(StrEnum):
    PREMIUM = "premium"
    DIVIDEND = "dividend"
    FEE = "fee"
    INTEREST = "interest"
    TRANSFER = "transfer"
    TRADE_SETTLEMENT = "trade_settlement"
    WITHHOLDING = "withholding"
    OTHER = "other"


class OptionLifecycleType(StrEnum):
    EXPIRATION = "expiration"
    ASSIGNMENT = "assignment"
    EXERCISE = "exercise"
    ADJUSTMENT = "adjustment"


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    external_key: str
    instrument_external_key: str
    occurred_at: datetime
    side: ExecutionSide
    position_effect: PositionEffect
    quantity: Decimal
    price: Decimal
    gross_amount: Decimal
    fees: Decimal
    net_cash: Decimal
    order_external_key: str | None = None

    def __post_init__(self) -> None:
        require_text(self.external_key, "external_key")
        require_text(self.instrument_external_key, "instrument_external_key")
        require_aware(self.occurred_at, "occurred_at")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        require_non_negative(self.price, "price")
        require_non_negative(self.gross_amount, "gross_amount")
        require_non_negative(self.fees, "fees")
        if self.order_external_key is not None:
            require_text(self.order_external_key, "order_external_key")


@dataclass(frozen=True, slots=True)
class CashMovementRecord:
    external_key: str
    occurred_at: datetime
    movement_type: CashMovementType
    amount: Decimal
    description: str
    instrument_external_key: str | None = None

    def __post_init__(self) -> None:
        require_text(self.external_key, "external_key")
        require_aware(self.occurred_at, "occurred_at")
        require_text(self.description, "description")
        if self.instrument_external_key is not None:
            require_text(self.instrument_external_key, "instrument_external_key")


@dataclass(frozen=True, slots=True)
class OptionLifecycleEventRecord:
    external_key: str
    option_instrument_external_key: str
    occurred_at: datetime
    event_type: OptionLifecycleType
    option_quantity: Decimal
    stock_instrument_external_key: str | None = None
    stock_quantity: Decimal | None = None
    cash_amount: Decimal | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_text(self.external_key, "external_key")
        require_text(self.option_instrument_external_key, "option_instrument_external_key")
        require_aware(self.occurred_at, "occurred_at")
        if self.option_quantity <= 0:
            raise ValueError("option_quantity must be positive")
        if self.stock_instrument_external_key is not None:
            require_text(self.stock_instrument_external_key, "stock_instrument_external_key")
        if self.stock_quantity is not None and self.stock_instrument_external_key is None:
            raise ValueError("stock_quantity requires stock_instrument_external_key")
        require_optional_non_negative(self.stock_quantity, "stock_quantity")


@dataclass(frozen=True, slots=True)
class LedgerActivityBatch:
    source: str
    account_external_key: str
    raw_event_id: str
    instruments: tuple[InstrumentRecord, ...]
    executions: tuple[ExecutionRecord, ...] = ()
    cash_movements: tuple[CashMovementRecord, ...] = ()
    lifecycle_events: tuple[OptionLifecycleEventRecord, ...] = ()

    def __post_init__(self) -> None:
        require_text(self.source, "source")
        require_text(self.account_external_key, "account_external_key")
        require_text(self.raw_event_id, "raw_event_id")
