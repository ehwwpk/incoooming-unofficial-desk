from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from schwab_dashboard.domain.instruments import AssetType, DeliverableKind
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


def test_adjusted_transaction_multiplier_does_not_become_a_share_deliverable() -> None:
    mapped = SchwabTransactionMapper().map(
        {
            "activityId": "adjusted-option",
            "time": "2026-08-10T15:30:00+00:00",
            "type": "TRADE",
            "netAmount": 148.70,
            "transferItems": [
                {
                    "amount": -1,
                    "cost": 150,
                    "price": 1,
                    "positionEffect": "OPENING",
                    "instrument": {
                        **OPTION,
                        "symbol": "KTOS1 260918C00075000",
                        "optionPremiumMultiplier": 150,
                        "nonStandard": True,
                    },
                }
            ],
        },
        observed_at=NOW,
    )

    instrument = mapped.instruments[0]
    assert instrument.contract_multiplier == Decimal("150")
    assert instrument.deliverable is not None
    assert instrument.deliverable.kind is DeliverableKind.ADJUSTED
    assert instrument.deliverable.components == ()


def test_trade_adjustment_attaches_to_first_emitted_security_item() -> None:
    mapped = SchwabTransactionMapper().map(
        {
            "activityId": "zero-item-first",
            "time": "2026-08-10T15:30:00+00:00",
            "type": "TRADE",
            "netAmount": 98.70,
            "transferItems": [
                {
                    "amount": 0,
                    "cost": 0,
                    "instrument": {"assetType": "EQUITY", "symbol": "IGNORED"},
                },
                {
                    "amount": -1,
                    "cost": 100,
                    "price": 1,
                    "positionEffect": "OPENING",
                    "instrument": OPTION,
                },
            ],
        },
        observed_at=NOW,
    )

    assert len(mapped.executions) == 1
    assert mapped.executions[0].external_key == "zero-item-first:item:1"
    assert mapped.executions[0].fees == Decimal("1.30")
    assert mapped.executions[0].net_cash == Decimal("98.70")


def test_asset_type_matching_is_case_insensitive() -> None:
    mapped = SchwabTransactionMapper().map(
        {
            "activityId": "lowercase-option",
            "time": "2026-08-10T15:30:00+00:00",
            "type": " trade ",
            "netAmount": 99,
            "transferItems": [
                {
                    "amount": -1,
                    "cost": 100,
                    "price": 1,
                    "positionEffect": " opening ",
                    "instrument": {
                        **OPTION,
                        "assetType": " option ",
                        "putCall": " call ",
                    },
                },
                {
                    "amount": 99,
                    "instrument": {"assetType": " currency ", "symbol": "USD"},
                },
            ],
        },
        observed_at=NOW,
    )

    assert len(mapped.instruments) == 1
    assert mapped.instruments[0].asset_type is AssetType.OPTION
    assert mapped.instruments[0].option_side is not None
    assert len(mapped.executions) == 1


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


def test_dividend_preserves_a_unique_security_and_journal_is_not_owner_capital() -> None:
    mapper = SchwabTransactionMapper()
    dividend = mapper.map(
        {
            "activityId": "div-security",
            "time": "2026-08-10T15:30:00Z",
            "type": "DIVIDEND_OR_INTEREST",
            "description": "Qualified dividend",
            "netAmount": 25,
            "transferItems": [
                {
                    "amount": 25,
                    "instrument": {
                        "assetType": "EQUITY",
                        "cusip": "50077B207",
                        "symbol": "KTOS",
                    },
                }
            ],
        },
        observed_at=NOW,
    )
    journal = mapper.map(
        {
            "activityId": "journal-1",
            "time": "2026-08-10T15:30:00Z",
            "type": "JOURNAL",
            "description": "Internal account adjustment",
            "netAmount": 100,
        },
        observed_at=NOW,
    )

    assert dividend.cash_movements[0].instrument_external_key == "50077B207"
    assert journal.cash_movements[0].movement_type is CashMovementType.OTHER


def test_explicit_schwab_cash_receipt_and_disbursement_are_owner_flows() -> None:
    mapper = SchwabTransactionMapper()
    receipt = mapper.map(
        {
            "activityId": "cash-receipt",
            "time": "2026-08-12T18:08:21Z",
            "type": "CASH_RECEIPT",
            "description": "Tfr EXTERNAL CREDIT UNION",
            "netAmount": 25000,
        },
        observed_at=NOW,
    )
    disbursement = mapper.map(
        {
            "activityId": "cash-disbursement",
            "time": "2026-08-13T18:08:21Z",
            "type": "CASH_DISBURSEMENT",
            "description": "Tfr EXTERNAL CREDIT UNION",
            "netAmount": -5000,
        },
        observed_at=NOW,
    )

    assert receipt.cash_movements[0].movement_type is CashMovementType.TRANSFER
    assert receipt.cash_movements[0].amount == Decimal("25000")
    assert disbursement.cash_movements[0].movement_type is CashMovementType.TRANSFER
    assert disbursement.cash_movements[0].amount == Decimal("-5000")


def test_schwab_cash_interest_abbreviation_is_not_a_dividend() -> None:
    mapped = SchwabTransactionMapper().map(
        {
            "activityId": "cash-interest",
            "time": "2026-08-29T00:10:32Z",
            "type": "DIVIDEND_OR_INTEREST",
            "description": "SCHWAB1 INT 07/30-08/27",
            "netAmount": 0.58,
        },
        observed_at=NOW,
    )

    assert mapped.cash_movements[0].movement_type is CashMovementType.INTEREST


@pytest.mark.parametrize(
    ("description", "expected"),
    (
        ("STOCK BORROW FEE/SPCE", CashMovementType.FEE),
        ("TRF FUNDS FRM TYPE 2", CashMovementType.TRADE_SETTLEMENT),
        ("TRF FUNDS TO TYPE 1", CashMovementType.TRADE_SETTLEMENT),
        ("UNEXPLAINED JOURNAL", CashMovementType.OTHER),
    ),
)
def test_schwab_journals_are_classified_only_when_their_role_is_known(
    description: str,
    expected: CashMovementType,
) -> None:
    mapped = SchwabTransactionMapper().map(
        {
            "activityId": description,
            "time": "2026-08-29T00:10:32Z",
            "type": "JOURNAL",
            "description": description,
            "netAmount": -3.72,
        },
        observed_at=NOW,
    )

    assert mapped.cash_movements[0].movement_type is expected


def test_date_only_transaction_remains_on_the_stated_market_date() -> None:
    mapped = SchwabTransactionMapper().map(
        {
            "activityId": "dated-1",
            "tradeDate": "2026-08-10",
            "type": "DIVIDEND_OR_INTEREST",
            "description": "Dividend",
            "netAmount": 1,
        },
        observed_at=NOW,
    )

    assert mapped.cash_movements[0].occurred_at.date().isoformat() == "2026-08-10"


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


def test_assignment_preserves_equity_delivery_and_cash_when_present() -> None:
    mapped = SchwabTransactionMapper().map(
        {
            "activityId": "assignment-delivery",
            "time": "2026-08-10T15:30:00Z",
            "type": "RECEIVE_AND_DELIVER",
            "description": "PUT ASSIGNMENT",
            "netAmount": -7500,
            "transferItems": [
                {
                    "amount": 1,
                    "positionEffect": "CLOSING",
                    "instrument": {**OPTION, "putCall": "PUT"},
                },
                {
                    "amount": 100,
                    "instrument": {
                        "assetType": "EQUITY",
                        "cusip": "50077B207",
                        "symbol": "KTOS",
                    },
                },
            ],
        },
        observed_at=NOW,
    )

    event = mapped.lifecycle_events[0]
    assert event.stock_instrument_external_key == "50077B207"
    assert event.stock_quantity == Decimal("100")
    assert event.cash_amount == Decimal("-7500")


def test_multi_option_lifecycle_does_not_duplicate_one_delivery_across_events() -> None:
    second_option = {**OPTION, "symbol": "KTOS  260918P00070000", "putCall": "PUT"}
    mapped = SchwabTransactionMapper().map(
        {
            "activityId": "multi-assignment",
            "time": "2026-08-10T15:30:00Z",
            "type": "RECEIVE_AND_DELIVER",
            "description": "PUT ASSIGNMENT",
            "netAmount": -14500,
            "transferItems": [
                {"amount": 1, "positionEffect": "CLOSING", "instrument": OPTION},
                {"amount": 1, "positionEffect": "CLOSING", "instrument": second_option},
                {
                    "amount": 200,
                    "instrument": {
                        "assetType": "EQUITY",
                        "cusip": "50077B207",
                        "symbol": "KTOS",
                    },
                },
            ],
        },
        observed_at=NOW,
    )

    assert len(mapped.lifecycle_events) == 2
    assert all(event.stock_quantity is None for event in mapped.lifecycle_events)
    assert all(event.cash_amount is None for event in mapped.lifecycle_events)
    assert all(event.details["delivery_ambiguous"] is True for event in mapped.lifecycle_events)
