from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from schwab_dashboard.domain.instruments import (
    AssetType,
    DeliverableComponent,
    DeliverableKind,
    InstrumentRecord,
    OptionDeliverable,
    OptionSide,
)
from schwab_dashboard.domain.ledger import CashMovementRecord, CashMovementType
from schwab_dashboard.domain.market import (
    InstrumentRef,
    MarkMethod,
    OptionMarketSnapshot,
    QuoteQuality,
)

NOW = datetime(2026, 8, 9, 19, 30, tzinfo=UTC)


def test_adjusted_option_deliverable_is_not_forced_to_one_hundred_shares() -> None:
    instrument = InstrumentRecord(
        source="schwab",
        external_key="adjusted-call-1",
        symbol="XYZ  260918C00065000",
        asset_type=AssetType.OPTION,
        observed_at=NOW,
        underlying_symbol="XYZ",
        option_side=OptionSide.CALL,
        expiration_date=date(2026, 9, 18),
        strike=Decimal("65"),
        contract_multiplier=Decimal("100"),
        deliverable=OptionDeliverable(
            kind=DeliverableKind.ADJUSTED,
            description="Corporate-action adjusted basket",
            components=(
                DeliverableComponent(
                    asset_type=AssetType.EQUITY,
                    symbol="XYZ",
                    quantity=Decimal("50"),
                ),
                DeliverableComponent(
                    asset_type=AssetType.CASH,
                    quantity=Decimal("1"),
                    cash_amount=Decimal("12.34"),
                    currency="USD",
                ),
            ),
        ),
    )

    assert instrument.deliverable is not None
    assert instrument.deliverable.components[0].quantity == Decimal("50")


def test_adjusted_status_can_be_known_before_the_exact_deliverable_is_known() -> None:
    deliverable = OptionDeliverable(kind=DeliverableKind.ADJUSTED, components=())

    assert deliverable.components == ()


def test_non_option_rejects_option_metadata() -> None:
    with pytest.raises(ValueError, match="only valid for option"):
        InstrumentRecord(
            source="schwab",
            external_key="equity-1",
            symbol="XYZ",
            asset_type=AssetType.EQUITY,
            observed_at=NOW,
            strike=Decimal("65"),
        )


def test_source_timestamps_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone"):
        CashMovementRecord(
            external_key="cash-1",
            occurred_at=datetime(2026, 8, 9, 12, 30),
            movement_type=CashMovementType.DIVIDEND,
            amount=Decimal("100"),
            description="Dividend",
        )


def test_missing_market_values_remain_distinct_from_zero() -> None:
    snapshot = OptionMarketSnapshot(
        instrument=InstrumentRef(source="schwab", external_key="call-1"),
        observed_at=NOW,
        quote_quality=QuoteQuality.ONE_SIDED,
        mark_method=MarkMethod.UNAVAILABLE,
        bid=Decimal("0"),
        ask=None,
        mark=None,
        open_interest=0,
    )

    assert snapshot.bid == Decimal("0")
    assert snapshot.ask is None
    assert snapshot.mark is None
    assert snapshot.open_interest == 0
