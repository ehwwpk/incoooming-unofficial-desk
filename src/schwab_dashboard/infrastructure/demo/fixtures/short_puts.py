"""Deterministic, fictional cash-secured puts for the public demo.

The $18,750 ending cash fixture already includes these opening credits. Full
strike collateral is $11,500; premiums do not reduce the cash-reserve test.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal

from schwab_dashboard.application.dashboard.cashflows import CashEvent
from schwab_dashboard.application.dashboard.performance import CashActivityItem

D = Decimal


@dataclass(frozen=True, slots=True)
class ShortPutFixture:
    record_id: str
    symbol: str
    opened_on: date
    expires_on: date
    strike: Decimal
    entry_credit_per_share: Decimal
    mark_per_share: Decimal
    bid_per_share: Decimal
    ask_per_share: Decimal
    day_profit_loss: Decimal
    implied_volatility_percent: Decimal
    delta: Decimal
    gamma: Decimal
    theta_per_share: Decimal
    vega: Decimal
    contracts: int = 1

    @property
    def option_symbol(self) -> str:
        return f"{self.symbol} {self.expires_on:%y%m%d}P{int(self.strike * 1000):08d}"

    @property
    def entry_credit(self) -> Decimal:
        return self.entry_credit_per_share * self.contracts * 100


PUT_FIXTURES = (
    ShortPutFixture(
        record_id="demo-ktos-put-0803-60",
        symbol="KTOS",
        opened_on=date(2026, 8, 3),
        expires_on=date(2026, 8, 28),
        strike=D("60"),
        entry_credit_per_share=D("3.50"),
        mark_per_share=D("2.90"),
        bid_per_share=D("2.85"),
        ask_per_share=D("2.95"),
        day_profit_loss=D("90"),
        implied_volatility_percent=D("58.6"),
        delta=D("-0.43"),
        gamma=D("0.046"),
        theta_per_share=D("-0.079"),
        vega=D("0.057"),
    ),
    ShortPutFixture(
        record_id="demo-urnm-put-0804-55",
        symbol="URNM",
        opened_on=date(2026, 8, 4),
        expires_on=date(2026, 8, 21),
        strike=D("55"),
        entry_credit_per_share=D("2.40"),
        mark_per_share=D("2.05"),
        bid_per_share=D("2.00"),
        ask_per_share=D("2.10"),
        day_profit_loss=D("65"),
        implied_volatility_percent=D("41.2"),
        delta=D("-0.52"),
        gamma=D("0.091"),
        theta_per_share=D("-0.061"),
        vega=D("0.043"),
    ),
)


def build_put_cash_events() -> tuple[CashEvent, ...]:
    return tuple(
        CashEvent(
            event_id=f"{item.record_id}:open",
            occurred_on=item.opened_on,
            symbol=item.symbol,
            event_type="OPENING CREDIT",
            amount=item.entry_credit,
            contracts=item.contracts,
        )
        for item in PUT_FIXTURES
    )


def build_put_executions() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "external_key": item.record_id,
            "order_external_key": item.record_id,
            "account_mask": "...4831",
            "occurred_at": datetime.combine(item.opened_on, time(16), tzinfo=UTC),
            "side": "sell",
            "position_effect": "opening",
            "asset_type": "option",
            "symbol": item.option_symbol,
            "underlying_symbol": item.symbol,
            "option_side": "put",
            "strike": item.strike,
            "expiration_date": item.expires_on,
            "quantity": D(item.contracts),
            "price": item.entry_credit_per_share,
            "contract_multiplier": D("100"),
            "is_non_standard": False,
            "gross_amount": item.entry_credit,
            "net_cash": item.entry_credit,
            "fees": D("0"),
        }
        for item in PUT_FIXTURES
    )


def build_put_cash_activity_items() -> tuple[CashActivityItem, ...]:
    return tuple(
        CashActivityItem(
            event_id=event.event_id,
            occurred_on=event.occurred_on,
            symbol=event.symbol,
            action_label="PUT SOLD",
            amount=event.amount,
            contracts=event.contracts,
            tone="credit",
            anchor_id=f"{event.symbol.lower()}-workspace",
        )
        for event in build_put_cash_events()
    )
