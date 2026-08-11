from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from schwab_dashboard.domain.ledger import (
    CashMovementType,
    ExecutionSide,
    OptionLifecycleType,
    PositionEffect,
)
from schwab_dashboard.infrastructure.schwab.transaction_mapper import SchwabTransactionMapper

NOW = datetime(2026, 8, 11, 18, tzinfo=UTC)
OPTION = {
    "assetType": "OPTION",
    "instrumentId": "option-id",
    "symbol": "KTOS  260918C00075000",
    "description": "KTOS Sep 18 2026 75 Call",
    "underlyingSymbol": "KTOS",
    "putCall": "CALL",
    "strikePrice": 75,
    "optionPremiumMultiplier": 100,
}


def test_maps_short_call_sale_with_observed_cash_and_fees() -> None:
    mapped = SchwabTransactionMapper().map(
        {
            "activityId": 123,
            "orderId": 99,
            "time": "2026-08-10T15:30:00+00:00",
            "type": "TRADE",
            "netAmount": 488.70,
            "transferItems": [
                {
                    "amount": -2,
                    "cost": 490,
                    "price": 2.45,
                    "positionEffect": "OPENING",
                    "instrument": OPTION,
                },
                {
                    "amount": 488.70,
                    "cost": -488.70,
                    "instrument": {"assetType": "CURRENCY", "symbol": "USD"},
                },
            ],
        },
        observed_at=NOW,
    )

    assert len(mapped.instruments) == 1
    assert mapped.instruments[0].underlying_symbol == "KTOS"
    execution = mapped.executions[0]
    assert execution.side is ExecutionSide.SELL
    assert execution.position_effect is PositionEffect.OPENING
    assert execution.quantity == Decimal("2")
    assert execution.price == Decimal("2.45")
    assert execution.gross_amount == Decimal("490")
    assert execution.fees == Decimal("1.30")
    assert execution.net_cash == Decimal("488.70")


def test_maps_dividend_and_margin_interest_separately() -> None:
    mapper = SchwabTransactionMapper()
    dividend = mapper.map(
        {
            "activityId": "div-1",
            "time": "2026-08-10T15:30:00Z",
            "type": "DIVIDEND_OR_INTEREST",
            "description": "Qualified cash payment",
            "netAmount": 125,
        },
        observed_at=NOW,
    )
    interest = mapper.map(
        {
            "activityId": "interest-1",
            "time": "2026-08-10T15:30:00Z",
            "type": "DIVIDEND_OR_INTEREST",
            "description": "Margin interest adjustment",
            "netAmount": -9,
        },
        observed_at=NOW,
    )

    assert dividend.cash_movements[0].movement_type is CashMovementType.DIVIDEND
    assert dividend.cash_movements[0].amount == Decimal("125")
    assert interest.cash_movements[0].movement_type is CashMovementType.INTEREST
    assert interest.cash_movements[0].amount == Decimal("-9")


def test_maps_assignment_and_expiration_as_lifecycle_not_cash() -> None:
    mapper = SchwabTransactionMapper()
    assignment = mapper.map(
        {
            "activityId": "assignment-1",
            "time": "2026-08-10T15:30:00Z",
            "type": "RECEIVE_AND_DELIVER",
            "description": "CALL ASSIGNMENT",
            "netAmount": 0,
            "transferItems": [
                {
                    "amount": 2,
                    "cost": 0,
                    "positionEffect": "CLOSING",
                    "instrument": OPTION,
                }
            ],
        },
        observed_at=NOW,
    )
    expiration = mapper.map(
        {
            "activityId": "expiration-1",
            "time": "2026-08-10T15:30:00Z",
            "type": "RECEIVE_AND_DELIVER",
            "description": "CALL EXPIRATION",
            "netAmount": 0,
            "transferItems": [
                {
                    "amount": 1,
                    "cost": 0,
                    "positionEffect": "CLOSING",
                    "instrument": OPTION,
                }
            ],
        },
        observed_at=NOW,
    )

    assert assignment.lifecycle_events[0].event_type is OptionLifecycleType.ASSIGNMENT
    assert assignment.lifecycle_events[0].option_quantity == Decimal("2")
    assert expiration.lifecycle_events[0].event_type is OptionLifecycleType.EXPIRATION
    assert not assignment.cash_movements
