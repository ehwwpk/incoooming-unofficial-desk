from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class BrokerAccount:
    external_key: str
    account_mask: str
    account_type: str

    def __post_init__(self) -> None:
        if not self.external_key.strip():
            raise ValueError("external_key must not be blank")
        if not self.account_mask.strip():
            raise ValueError("account_mask must not be blank")


@dataclass(frozen=True, slots=True)
class BrokerPosition:
    instrument_key: str
    symbol: str
    asset_type: str
    long_quantity: Decimal
    short_quantity: Decimal
    average_price: Decimal | None = None
    market_value: Decimal | None = None
    day_profit_loss: Decimal | None = None
    day_profit_loss_percent: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.instrument_key.strip():
            raise ValueError("instrument_key must not be blank")
        if not self.symbol.strip():
            raise ValueError("symbol must not be blank")
        if self.long_quantity < 0 or self.short_quantity < 0:
            raise ValueError("broker long and short quantities must be non-negative")

    @property
    def net_quantity(self) -> Decimal:
        return self.long_quantity - self.short_quantity
