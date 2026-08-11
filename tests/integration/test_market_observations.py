from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from schwab_dashboard.application.errors import SourceRecordConflictError
from schwab_dashboard.application.services.record_market_observations import (
    RecordMarketObservations,
)
from schwab_dashboard.domain.instruments import AssetType, InstrumentRecord, OptionSide
from schwab_dashboard.domain.market import (
    InstrumentRef,
    MarketObservationBatch,
    MarkMethod,
    OptionMarketSnapshot,
    QuoteQuality,
    UnderlyingMarketSnapshot,
)
from schwab_dashboard.infrastructure.database.analytics_reader import SqlLiveAnalyticsReader
from schwab_dashboard.infrastructure.database.tables import (
    InstrumentTable,
    OptionMarketSnapshotTable,
    RawMarketEventTable,
    UnderlyingMarketSnapshotTable,
)
from schwab_dashboard.infrastructure.database.uow_market import build_market_uow_factory

NOW = datetime(2026, 8, 9, 19, 45, tzinfo=UTC)


def _batch(*, option_mark: str = "3.30") -> MarketObservationBatch:
    equity_ref = InstrumentRef(source="schwab", external_key="equity-ktos")
    option_ref = InstrumentRef(source="schwab", external_key="call-ktos-65")
    return MarketObservationBatch(
        source="schwab",
        external_event_key="quotes-2026-08-09T19:45:00Z",
        observed_at=NOW,
        parser_version="test-v1",
        raw_payload={"quoteCount": 2, "optionMark": option_mark},
        instruments=(
            InstrumentRecord(
                source="schwab",
                external_key=equity_ref.external_key,
                symbol="KTOS",
                asset_type=AssetType.EQUITY,
                observed_at=NOW,
            ),
            InstrumentRecord(
                source="schwab",
                external_key=option_ref.external_key,
                symbol="KTOS  260918C00065000",
                asset_type=AssetType.OPTION,
                observed_at=NOW,
                underlying_symbol="KTOS",
                option_side=OptionSide.CALL,
                expiration_date=date(2026, 9, 18),
                strike=Decimal("65"),
                contract_multiplier=Decimal("100"),
            ),
        ),
        underlying_snapshots=(
            UnderlyingMarketSnapshot(
                instrument=equity_ref,
                observed_at=NOW,
                quote_quality=QuoteQuality.COMPLETE,
                mark_method=MarkMethod.MIDPOINT,
                bid=Decimal("60.76"),
                ask=Decimal("60.78"),
                last=Decimal("60.77"),
                mark=Decimal("60.77"),
                previous_close=Decimal("59.50"),
            ),
        ),
        option_snapshots=(
            OptionMarketSnapshot(
                instrument=option_ref,
                observed_at=NOW,
                quote_quality=QuoteQuality.COMPLETE,
                mark_method=MarkMethod.BROKER,
                bid=Decimal("3.20"),
                ask=Decimal("3.40"),
                mark=Decimal(option_mark),
                underlying_price=Decimal("60.77"),
                implied_volatility=Decimal("0.586"),
                delta=Decimal("0.41"),
                gamma=Decimal("0.022"),
                theta=Decimal("-0.065"),
                vega=Decimal("0.104"),
                volume=17,
                open_interest=842,
            ),
        ),
    )


def test_market_observation_preserves_raw_payload_and_point_in_time_values(
    database_runtime: tuple[object, object, object],
) -> None:
    _, session_factory, _ = database_runtime
    service = RecordMarketObservations(
        uow_factory=build_market_uow_factory(session_factory),  # type: ignore[arg-type]
    )

    result = service.execute(_batch())
    service.execute(_batch())

    assert result.underlying_snapshot_count == 1
    assert result.option_snapshot_count == 1
    with session_factory() as session:  # type: ignore[operator]
        assert session.scalar(select(func.count()).select_from(RawMarketEventTable)) == 1
        assert session.scalar(select(func.count()).select_from(InstrumentTable)) == 2
        assert session.scalar(select(func.count()).select_from(UnderlyingMarketSnapshotTable)) == 1
        assert session.scalar(select(func.count()).select_from(OptionMarketSnapshotTable)) == 1
        option = session.scalar(select(OptionMarketSnapshotTable))
        assert option is not None
        assert option.mark == Decimal("3.3000000000")
        assert option.theta == Decimal("-0.0650000000")


def test_same_market_event_identity_cannot_change_payload(
    database_runtime: tuple[object, object, object],
) -> None:
    _, session_factory, _ = database_runtime
    service = RecordMarketObservations(
        uow_factory=build_market_uow_factory(session_factory),  # type: ignore[arg-type]
    )
    service.execute(_batch())

    with pytest.raises(SourceRecordConflictError, match="payload"):
        service.execute(_batch(option_mark="3.31"))


def test_latest_reader_uses_retrieval_time_when_exchange_timestamp_is_unchanged(
    database_runtime: tuple[object, object, object],
) -> None:
    _, session_factory, _ = database_runtime
    service = RecordMarketObservations(
        uow_factory=build_market_uow_factory(session_factory),  # type: ignore[arg-type]
    )
    service.execute(_batch(option_mark="3.30"))
    later = replace(
        _batch(option_mark="3.31"),
        external_event_key="quotes-2026-08-09T19:46:00Z",
        observed_at=NOW + timedelta(minutes=1),
    )
    service.execute(later)

    rows = SqlLiveAnalyticsReader(session_factory).list_latest_option_market()  # type: ignore[arg-type]

    assert len(rows) == 1
    assert rows[0]["mark"] == Decimal("3.3100000000")
