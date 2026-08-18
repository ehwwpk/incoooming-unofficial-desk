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
    UnderlyingDailyBar,
    UnderlyingIntradayBar,
    UnderlyingMarketSnapshot,
)
from schwab_dashboard.infrastructure.database.analytics_reader import SqlLiveAnalyticsReader
from schwab_dashboard.infrastructure.database.tables import (
    InstrumentTable,
    OptionMarketSnapshotTable,
    RawMarketEventTable,
    UnderlyingDailyBarTable,
    UnderlyingIntradayBarTable,
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


def test_latest_reader_deterministically_breaks_equal_retrieval_time_ties(
    database_runtime: tuple[object, object, object],
) -> None:
    _, session_factory, _ = database_runtime
    service = RecordMarketObservations(
        uow_factory=build_market_uow_factory(session_factory),  # type: ignore[arg-type]
    )
    daily_bar = UnderlyingDailyBar(
        instrument=InstrumentRef(source="schwab", external_key="equity-ktos"),
        trade_date=date(2026, 8, 9),
        open=Decimal("59.50"),
        high=Decimal("60.80"),
        low=Decimal("59.25"),
        close=Decimal("60.77"),
        volume=1_000,
    )
    first = replace(
        _batch(option_mark="3.30"),
        raw_payload={"version": "first"},
        daily_bars=(daily_bar,),
    )
    second = replace(
        first,
        external_event_key="quotes-2026-08-09T19:45:00Z-second",
        raw_payload={"version": "second"},
        underlying_snapshots=(
            replace(
                first.underlying_snapshots[0],
                bid=Decimal("60.99"),
                ask=Decimal("61.01"),
                last=Decimal("61.00"),
                mark=Decimal("61.00"),
            ),
        ),
        option_snapshots=(
            replace(first.option_snapshots[0], mark=Decimal("3.31")),
        ),
        daily_bars=(
            replace(
                daily_bar,
                high=Decimal("61.10"),
                close=Decimal("61.00"),
                volume=1_100,
            ),
        ),
    )
    service.execute(first)
    service.execute(second)

    with session_factory() as session:  # type: ignore[operator]
        events = {
            event.external_event_key: event
            for event in session.scalars(select(RawMarketEventTable)).all()
        }
        events[first.external_event_key].created_at = NOW
        events[second.external_event_key].created_at = NOW + timedelta(minutes=1)
        session.commit()

    reader = SqlLiveAnalyticsReader(session_factory)  # type: ignore[arg-type]

    assert reader.list_latest_underlying_market()[0]["mark"] == Decimal("61.0000000000")
    assert reader.list_latest_option_market()[0]["mark"] == Decimal("3.3100000000")
    assert reader.list_daily_bars()[0]["close"] == Decimal("61.0000000000")


def test_unchanged_price_history_is_reused_across_syncs(
    database_runtime: tuple[object, object, object],
) -> None:
    _, session_factory, _ = database_runtime
    service = RecordMarketObservations(
        uow_factory=build_market_uow_factory(session_factory),  # type: ignore[arg-type]
    )
    reference = InstrumentRef(source="schwab", external_key="market:SPY")
    instrument = InstrumentRecord(
        source="schwab",
        external_key="market:SPY",
        symbol="SPY",
        asset_type=AssetType.ETF,
        observed_at=NOW,
    )
    bar = UnderlyingDailyBar(
        instrument=reference,
        trade_date=date(2026, 8, 8),
        open=Decimal("640"),
        high=Decimal("645"),
        low=Decimal("639"),
        close=Decimal("644"),
        volume=1000,
    )
    first = MarketObservationBatch(
        source="schwab",
        external_event_key="history:SPY:first",
        observed_at=NOW,
        parser_version="test-v1",
        raw_payload={"symbol": "SPY", "candles": [{"close": 644}]},
        instruments=(instrument,),
        daily_bars=(bar,),
    )
    second = replace(
        first,
        external_event_key="history:SPY:second",
        observed_at=NOW + timedelta(minutes=1),
        instruments=(replace(instrument, observed_at=NOW + timedelta(minutes=1)),),
    )

    service.execute(first)
    service.execute(second)

    with session_factory() as session:  # type: ignore[operator]
        assert session.scalar(select(func.count()).select_from(RawMarketEventTable)) == 1
        assert session.scalar(select(func.count()).select_from(UnderlyingDailyBarTable)) == 1


def test_unchanged_intraday_history_is_reused_across_syncs(
    database_runtime: tuple[object, object, object],
) -> None:
    _, session_factory, _ = database_runtime
    service = RecordMarketObservations(
        uow_factory=build_market_uow_factory(session_factory),  # type: ignore[arg-type]
    )
    reference = InstrumentRef(source="schwab", external_key="market:CVX")
    instrument = InstrumentRecord(
        source="schwab",
        external_key="market:CVX",
        symbol="CVX",
        asset_type=AssetType.EQUITY,
        observed_at=NOW,
    )
    bar = UnderlyingIntradayBar(
        instrument=reference,
        started_at=NOW - timedelta(minutes=30),
        interval_minutes=30,
        open=Decimal("196"),
        high=Decimal("197"),
        low=Decimal("195.5"),
        close=Decimal("196.5"),
        volume=1000,
    )
    first = MarketObservationBatch(
        source="schwab",
        external_event_key="intraday:30m:CVX:first",
        observed_at=NOW,
        parser_version="test-v1",
        raw_payload={"symbol": "CVX", "candles": [{"close": 196.5}]},
        instruments=(instrument,),
        intraday_bars=(bar,),
    )
    second = replace(
        first,
        external_event_key="intraday:30m:CVX:second",
        observed_at=NOW + timedelta(minutes=1),
        instruments=(replace(instrument, observed_at=NOW + timedelta(minutes=1)),),
    )

    service.execute(first)
    service.execute(second)

    with session_factory() as session:  # type: ignore[operator]
        assert session.scalar(select(func.count()).select_from(RawMarketEventTable)) == 1
        assert session.scalar(select(func.count()).select_from(UnderlyingIntradayBarTable)) == 1


def test_revised_intraday_bar_keeps_a_new_version_and_reads_the_latest(
    database_runtime: tuple[object, object, object],
) -> None:
    _, session_factory, _ = database_runtime
    service = RecordMarketObservations(
        uow_factory=build_market_uow_factory(session_factory),  # type: ignore[arg-type]
    )
    reference = InstrumentRef(source="schwab", external_key="market:CVX")
    instrument = InstrumentRecord(
        source="schwab",
        external_key="market:CVX",
        symbol="CVX",
        asset_type=AssetType.EQUITY,
        observed_at=NOW,
    )
    first_bar = UnderlyingIntradayBar(
        instrument=reference,
        started_at=NOW - timedelta(minutes=30),
        interval_minutes=30,
        open=Decimal("196"),
        high=Decimal("197"),
        low=Decimal("195.5"),
        close=Decimal("196.5"),
        volume=1000,
    )
    first = MarketObservationBatch(
        source="schwab",
        external_event_key="intraday:30m:CVX:first",
        observed_at=NOW,
        parser_version="test-v1",
        raw_payload={"symbol": "CVX", "candles": [{"close": 196.5}]},
        instruments=(instrument,),
        intraday_bars=(first_bar,),
    )
    second = replace(
        first,
        external_event_key="intraday:30m:CVX:second",
        observed_at=NOW + timedelta(minutes=1),
        raw_payload={"symbol": "CVX", "candles": [{"close": 196.75}]},
        instruments=(replace(instrument, observed_at=NOW + timedelta(minutes=1)),),
        intraday_bars=(replace(first_bar, close=Decimal("196.75"), volume=1200),),
    )

    service.execute(first)
    service.execute(second)

    rows = SqlLiveAnalyticsReader(session_factory).list_intraday_bars(symbols=["CVX"])
    assert len(rows) == 1
    assert rows[0]["close"] == Decimal("196.7500000000")
    assert rows[0]["volume"] == 1200
    with session_factory() as session:  # type: ignore[operator]
        assert session.scalar(select(func.count()).select_from(UnderlyingIntradayBarTable)) == 2


def test_latest_option_market_unions_held_symbols_with_the_later_underlying_chain(
    database_runtime: tuple[object, object, object],
) -> None:
    _, session_factory, _ = database_runtime
    service = RecordMarketObservations(
        uow_factory=build_market_uow_factory(session_factory),  # type: ignore[arg-type]
    )
    held_ref = InstrumentRef(source="schwab", external_key="call-ktos-held")
    chain_ref = InstrumentRef(source="schwab", external_key="call-ktos-chain")
    batch = MarketObservationBatch(
        source="schwab",
        external_event_key="chain-union-2026-08-09T19:45:00Z",
        observed_at=NOW,
        parser_version="test-v1",
        raw_payload={"quoteCount": 2},
        instruments=(
            InstrumentRecord(
                source="schwab",
                external_key=held_ref.external_key,
                symbol="KTOS  260821C00065000",
                asset_type=AssetType.OPTION,
                observed_at=NOW,
                underlying_symbol="KTOS",
                option_side=OptionSide.CALL,
                expiration_date=date(2026, 8, 21),
                strike=Decimal("65"),
                contract_multiplier=Decimal("100"),
            ),
            InstrumentRecord(
                source="schwab",
                external_key=chain_ref.external_key,
                symbol="KTOS  260828C00070000",
                asset_type=AssetType.OPTION,
                observed_at=NOW,
                underlying_symbol="KTOS",
                option_side=OptionSide.CALL,
                expiration_date=date(2026, 8, 28),
                strike=Decimal("70"),
                contract_multiplier=Decimal("100"),
            ),
        ),
        option_snapshots=(
            OptionMarketSnapshot(
                instrument=held_ref,
                observed_at=NOW,
                quote_quality=QuoteQuality.COMPLETE,
                mark_method=MarkMethod.BROKER,
                bid=Decimal("1.10"),
                ask=Decimal("1.20"),
                mark=Decimal("1.15"),
            ),
            OptionMarketSnapshot(
                instrument=chain_ref,
                observed_at=NOW,
                quote_quality=QuoteQuality.COMPLETE,
                mark_method=MarkMethod.BROKER,
                bid=Decimal("0.80"),
                ask=Decimal("0.90"),
                mark=Decimal("0.85"),
            ),
        ),
    )
    service.execute(batch)
    reader = SqlLiveAnalyticsReader(session_factory)  # type: ignore[arg-type]

    held_only = reader.list_latest_option_market(symbols=["KTOS  260821C00065000"])
    union = reader.list_latest_option_market(
        symbols=["KTOS  260821C00065000"],
        underlyings=["KTOS"],
        expiration_on_or_after=date(2026, 8, 9),
    )

    assert {row["symbol"] for row in held_only} == {"KTOS  260821C00065000"}
    assert {row["symbol"] for row in union} == {
        "KTOS  260821C00065000",
        "KTOS  260828C00070000",
    }
