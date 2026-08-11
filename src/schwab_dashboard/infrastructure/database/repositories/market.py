from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from schwab_dashboard.application.ports.market import (
    OptionMarketSnapshotWrite,
    UnderlyingDailyBarWrite,
    UnderlyingMarketSnapshotWrite,
)
from schwab_dashboard.infrastructure.database.repositories.idempotency import (
    ensure_immutable_match,
)
from schwab_dashboard.infrastructure.database.tables.market import (
    OptionMarketSnapshotTable,
    RawMarketEventTable,
    UnderlyingDailyBarTable,
    UnderlyingMarketSnapshotTable,
)


class SqlRawMarketEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        *,
        source: str,
        external_event_key: str,
        observed_at: datetime,
        parser_version: str,
        payload: dict[str, Any],
    ) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        payload_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        row = self._session.scalar(
            select(RawMarketEventTable).where(
                RawMarketEventTable.source == source,
                RawMarketEventTable.external_event_key == external_event_key,
            )
        )
        if row is not None:
            ensure_immutable_match(
                row,
                {"observed_at": observed_at, "payload_hash": payload_hash, "payload": payload},
                identity=f"market:{external_event_key}",
            )
            return row.id
        row = RawMarketEventTable(
            source=source,
            external_event_key=external_event_key,
            observed_at=observed_at,
            parser_version=parser_version,
            payload_hash=payload_hash,
            payload=payload,
        )
        self._session.add(row)
        self._session.flush()
        return row.id


class SqlUnderlyingMarketSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, item: UnderlyingMarketSnapshotWrite) -> str:
        snapshot = item.snapshot
        expected = {
            "observed_at": snapshot.observed_at,
            "quote_quality": snapshot.quote_quality.value,
            "mark_method": snapshot.mark_method.value,
            "bid": snapshot.bid,
            "ask": snapshot.ask,
            "last": snapshot.last,
            "mark": snapshot.mark,
            "previous_close": snapshot.previous_close,
        }
        row = self._session.scalar(
            select(UnderlyingMarketSnapshotTable).where(
                UnderlyingMarketSnapshotTable.raw_event_id == item.raw_event_id,
                UnderlyingMarketSnapshotTable.instrument_id == item.instrument_id,
            )
        )
        if row is not None:
            ensure_immutable_match(row, expected, identity=f"underlying-snapshot:{row.id}")
            return row.id
        row = UnderlyingMarketSnapshotTable(
            raw_event_id=item.raw_event_id,
            instrument_id=item.instrument_id,
            **expected,
        )
        self._session.add(row)
        self._session.flush()
        return row.id


class SqlOptionMarketSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, item: OptionMarketSnapshotWrite) -> str:
        snapshot = item.snapshot
        expected = {
            "observed_at": snapshot.observed_at,
            "quote_quality": snapshot.quote_quality.value,
            "mark_method": snapshot.mark_method.value,
            "bid": snapshot.bid,
            "ask": snapshot.ask,
            "last": snapshot.last,
            "mark": snapshot.mark,
            "underlying_price": snapshot.underlying_price,
            "implied_volatility": snapshot.implied_volatility,
            "delta": snapshot.delta,
            "gamma": snapshot.gamma,
            "theta": snapshot.theta,
            "vega": snapshot.vega,
            "rho": snapshot.rho,
            "volume": snapshot.volume,
            "open_interest": snapshot.open_interest,
        }
        row = self._session.scalar(
            select(OptionMarketSnapshotTable).where(
                OptionMarketSnapshotTable.raw_event_id == item.raw_event_id,
                OptionMarketSnapshotTable.instrument_id == item.instrument_id,
            )
        )
        if row is not None:
            ensure_immutable_match(row, expected, identity=f"option-snapshot:{row.id}")
            return row.id
        row = OptionMarketSnapshotTable(
            raw_event_id=item.raw_event_id,
            instrument_id=item.instrument_id,
            **expected,
        )
        self._session.add(row)
        self._session.flush()
        return row.id


class SqlUnderlyingDailyBarRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, item: UnderlyingDailyBarWrite) -> str:
        bar = item.bar
        expected = {
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        row = self._session.scalar(
            select(UnderlyingDailyBarTable).where(
                UnderlyingDailyBarTable.raw_event_id == item.raw_event_id,
                UnderlyingDailyBarTable.instrument_id == item.instrument_id,
                UnderlyingDailyBarTable.trade_date == bar.trade_date,
            )
        )
        if row is not None:
            ensure_immutable_match(row, expected, identity=f"daily-bar:{row.id}")
            return row.id
        row = UnderlyingDailyBarTable(
            raw_event_id=item.raw_event_id,
            instrument_id=item.instrument_id,
            trade_date=bar.trade_date,
            **expected,
        )
        self._session.add(row)
        self._session.flush()
        return row.id
