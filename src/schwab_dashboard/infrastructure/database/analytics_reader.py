from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from schwab_dashboard.infrastructure.database.engine import SessionFactory
from schwab_dashboard.infrastructure.database.publication import (
    published_account_sync_run_ids,
    published_activity_sync_run_ids,
)
from schwab_dashboard.infrastructure.database.tables.account import (
    AccountBalanceSnapshotTable,
    AccountTable,
    PositionSnapshotTable,
)
from schwab_dashboard.infrastructure.database.tables.instrument import InstrumentTable
from schwab_dashboard.infrastructure.database.tables.ledger import (
    CashMovementTable,
    ExecutionTable,
    OptionLifecycleEventTable,
)
from schwab_dashboard.infrastructure.database.tables.market import (
    OptionMarketSnapshotTable,
    RawMarketEventTable,
    UnderlyingDailyBarTable,
    UnderlyingIntradayBarTable,
    UnderlyingMarketSnapshotTable,
)
from schwab_dashboard.infrastructure.database.tables.sync import RawBrokerEventTable, SyncRunTable


class SqlLiveAnalyticsReader:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def list_balance_history(self) -> tuple[dict[str, Any], ...]:
        with self._session_factory() as session:
            query = (
                select(AccountBalanceSnapshotTable, AccountTable)
                .join(AccountTable, AccountTable.id == AccountBalanceSnapshotTable.account_id)
                .join(SyncRunTable, SyncRunTable.id == AccountBalanceSnapshotTable.sync_run_id)
                .where(SyncRunTable.status == "completed")
                .order_by(AccountBalanceSnapshotTable.observed_at, AccountTable.account_mask)
            )
            published_run_ids = published_account_sync_run_ids(session)
            if published_run_ids == ():
                return ()
            if published_run_ids is not None:
                query = query.where(AccountBalanceSnapshotTable.sync_run_id.in_(published_run_ids))
            rows = session.execute(query).all()
        return tuple(
            {
                "account_id": account.id,
                "sync_run_id": balance.sync_run_id,
                "account_mask": account.account_mask,
                "observed_at": balance.observed_at,
                "liquidation_value": balance.liquidation_value,
                "initial_liquidation_value": balance.initial_liquidation_value,
                "equity": balance.equity,
                "cash_balance": balance.cash_balance,
                "margin_balance": balance.margin_balance,
                "buying_power": balance.buying_power,
                "available_funds": balance.available_funds,
                "maintenance_requirement": balance.maintenance_requirement,
                "long_market_value": balance.long_market_value,
                "short_market_value": balance.short_market_value,
                "long_option_market_value": balance.long_option_market_value,
                "short_option_market_value": balance.short_option_market_value,
            }
            for balance, account in rows
        )

    def list_position_history(self) -> tuple[dict[str, Any], ...]:
        with self._session_factory() as session:
            query = (
                select(PositionSnapshotTable, AccountTable, InstrumentTable)
                .join(AccountTable, AccountTable.id == PositionSnapshotTable.account_id)
                .outerjoin(
                    InstrumentTable,
                    and_(
                        InstrumentTable.source == AccountTable.source,
                        InstrumentTable.external_key == PositionSnapshotTable.instrument_key,
                    ),
                )
                .join(SyncRunTable, SyncRunTable.id == PositionSnapshotTable.sync_run_id)
                .where(SyncRunTable.status == "completed")
                .order_by(PositionSnapshotTable.observed_at, AccountTable.account_mask)
            )
            published_run_ids = published_account_sync_run_ids(session)
            if published_run_ids == ():
                return ()
            if published_run_ids is not None:
                query = query.where(PositionSnapshotTable.sync_run_id.in_(published_run_ids))
            rows = session.execute(query).all()
            option_metadata = _canonical_option_metadata(session)
        result: list[dict[str, Any]] = []
        for position, account, instrument in rows:
            contract_multiplier, is_non_standard = _position_option_metadata(
                position,
                instrument,
                option_metadata,
            )
            result.append(
                {
                    "account_id": account.id,
                    "sync_run_id": position.sync_run_id,
                    "account_mask": account.account_mask,
                    "observed_at": position.observed_at,
                    "symbol": position.symbol,
                    "asset_type": position.asset_type,
                    "net_quantity": position.long_quantity - position.short_quantity,
                    "average_price": position.average_price,
                    "market_value": position.market_value,
                    "long_open_profit_loss": position.long_open_profit_loss,
                    "short_open_profit_loss": position.short_open_profit_loss,
                    "underlying_symbol": position.underlying_symbol,
                    "option_type": position.option_type,
                    "expiration_date": position.expiration_date,
                    "strike": position.strike,
                    "contract_multiplier": contract_multiplier,
                    "is_non_standard": is_non_standard,
                    "deliverable": instrument.deliverable if instrument is not None else None,
                }
            )
        return tuple(result)

    def list_executions(self) -> tuple[dict[str, Any], ...]:
        with self._session_factory() as session:
            query = (
                select(ExecutionTable, InstrumentTable, AccountTable)
                .join(InstrumentTable, InstrumentTable.id == ExecutionTable.instrument_id)
                .join(AccountTable, AccountTable.id == ExecutionTable.account_id)
                .join(RawBrokerEventTable, RawBrokerEventTable.id == ExecutionTable.raw_event_id)
                .join(SyncRunTable, SyncRunTable.id == RawBrokerEventTable.sync_run_id)
                .where(SyncRunTable.status == "completed")
                .order_by(ExecutionTable.occurred_at)
            )
            published_run_ids = published_activity_sync_run_ids(session)
            if published_run_ids == ():
                return ()
            if published_run_ids is not None:
                query = query.where(SyncRunTable.id.in_(published_run_ids))
            rows = session.execute(query).all()
            option_metadata = _canonical_option_metadata(session)
        return tuple(
            {
                "account_id": account.id,
                "external_key": execution.external_key,
                "order_external_key": execution.order_external_key,
                "occurred_at": execution.occurred_at,
                "side": execution.side,
                "position_effect": execution.position_effect,
                "quantity": execution.quantity,
                "price": execution.price,
                "gross_amount": execution.gross_amount,
                "fees": execution.fees,
                "net_cash": execution.net_cash,
                "account_mask": account.account_mask,
                **_instrument_values(instrument, option_metadata),
            }
            for execution, instrument, account in rows
        )

    def list_cash_movements(self) -> tuple[dict[str, Any], ...]:
        with self._session_factory() as session:
            query = (
                select(CashMovementTable, InstrumentTable, AccountTable)
                .outerjoin(InstrumentTable, InstrumentTable.id == CashMovementTable.instrument_id)
                .join(AccountTable, AccountTable.id == CashMovementTable.account_id)
                .join(RawBrokerEventTable, RawBrokerEventTable.id == CashMovementTable.raw_event_id)
                .join(SyncRunTable, SyncRunTable.id == RawBrokerEventTable.sync_run_id)
                .where(SyncRunTable.status == "completed")
                .order_by(CashMovementTable.occurred_at)
            )
            published_run_ids = published_activity_sync_run_ids(session)
            if published_run_ids == ():
                return ()
            if published_run_ids is not None:
                query = query.where(SyncRunTable.id.in_(published_run_ids))
            rows = session.execute(query).all()
        return tuple(
            {
                "account_id": account.id,
                "external_key": movement.external_key,
                "occurred_at": movement.occurred_at,
                "movement_type": movement.movement_type,
                "amount": movement.amount,
                "description": movement.description,
                "account_mask": account.account_mask,
                "symbol": instrument.symbol if instrument is not None else None,
                "underlying_symbol": (
                    instrument.underlying_symbol if instrument is not None else None
                ),
            }
            for movement, instrument, account in rows
        )

    def list_lifecycle_events(self) -> tuple[dict[str, Any], ...]:
        stock_instrument = aliased(InstrumentTable)
        with self._session_factory() as session:
            query = (
                select(
                    OptionLifecycleEventTable,
                    InstrumentTable,
                    AccountTable,
                    stock_instrument,
                )
                .join(
                    InstrumentTable,
                    InstrumentTable.id == OptionLifecycleEventTable.option_instrument_id,
                )
                .join(AccountTable, AccountTable.id == OptionLifecycleEventTable.account_id)
                .join(
                    RawBrokerEventTable,
                    RawBrokerEventTable.id == OptionLifecycleEventTable.raw_event_id,
                )
                .join(SyncRunTable, SyncRunTable.id == RawBrokerEventTable.sync_run_id)
                .outerjoin(
                    stock_instrument,
                    stock_instrument.id == OptionLifecycleEventTable.stock_instrument_id,
                )
                .where(SyncRunTable.status == "completed")
                .order_by(OptionLifecycleEventTable.occurred_at)
            )
            published_run_ids = published_activity_sync_run_ids(session)
            if published_run_ids == ():
                return ()
            if published_run_ids is not None:
                query = query.where(SyncRunTable.id.in_(published_run_ids))
            rows = session.execute(query).all()
            option_metadata = _canonical_option_metadata(session)
        return tuple(
            {
                "account_id": account.id,
                "external_key": event.external_key,
                "occurred_at": event.occurred_at,
                "event_type": event.event_type,
                "option_quantity": event.option_quantity,
                "stock_quantity": event.stock_quantity,
                "cash_amount": event.cash_amount,
                "details": event.details,
                "stock_symbol": stock.symbol if stock is not None else None,
                "account_mask": account.account_mask,
                **_instrument_values(instrument, option_metadata),
            }
            for event, instrument, account, stock in rows
        )

    def list_latest_option_market(
        self,
        *,
        symbols: Sequence[str] | None = None,
        underlyings: Sequence[str] | None = None,
        expiration_on_or_after: date | None = None,
    ) -> tuple[dict[str, Any], ...]:
        normalized_symbols = _normalized_symbols(symbols)
        normalized_underlyings = _normalized_symbols(underlyings)
        if symbols is not None and not normalized_symbols and not normalized_underlyings:
            return ()
        if underlyings is not None and not normalized_underlyings and symbols is None:
            return ()
        instrument_ids = self._instrument_ids_for_option_market(
            symbols=normalized_symbols,
            underlyings=normalized_underlyings,
            expiration_on_or_after=expiration_on_or_after,
            unbounded=symbols is None and underlyings is None,
        )
        if instrument_ids is not None and not instrument_ids:
            return ()
        latest_retrieval_query = (
            select(
                OptionMarketSnapshotTable.instrument_id,
                func.max(RawMarketEventTable.observed_at).label("latest_at"),
            )
            .join(
                RawMarketEventTable,
                RawMarketEventTable.id == OptionMarketSnapshotTable.raw_event_id,
            )
            .group_by(OptionMarketSnapshotTable.instrument_id)
        )
        if instrument_ids is not None:
            latest_retrieval_query = latest_retrieval_query.where(
                OptionMarketSnapshotTable.instrument_id.in_(instrument_ids)
            )
        latest_retrieval = latest_retrieval_query.subquery()
        ranked_query = (
            select(
                OptionMarketSnapshotTable.id.label("snapshot_id"),
                func.row_number()
                .over(
                    partition_by=OptionMarketSnapshotTable.instrument_id,
                    order_by=(
                        RawMarketEventTable.observed_at.desc(),
                        RawMarketEventTable.created_at.desc(),
                        OptionMarketSnapshotTable.created_at.desc(),
                        OptionMarketSnapshotTable.raw_event_id.desc(),
                        OptionMarketSnapshotTable.id.desc(),
                    ),
                )
                .label("version_rank"),
            )
            .join(
                RawMarketEventTable,
                RawMarketEventTable.id == OptionMarketSnapshotTable.raw_event_id,
            )
            .join(
                latest_retrieval,
                and_(
                    latest_retrieval.c.instrument_id == OptionMarketSnapshotTable.instrument_id,
                    latest_retrieval.c.latest_at == RawMarketEventTable.observed_at,
                ),
            )
        )
        ranked = ranked_query.subquery()
        with self._session_factory() as session:
            query = (
                select(OptionMarketSnapshotTable, InstrumentTable)
                .join(
                    InstrumentTable,
                    InstrumentTable.id == OptionMarketSnapshotTable.instrument_id,
                )
                .join(
                    ranked,
                    ranked.c.snapshot_id == OptionMarketSnapshotTable.id,
                )
                .where(ranked.c.version_rank == 1)
            )
            rows = session.execute(query).all()
        return _dedupe_option_market_rows(
            tuple(
                {
                    **_instrument_values(instrument),
                    "observed_at": snapshot.observed_at,
                    "quote_quality": snapshot.quote_quality,
                    "mark_method": snapshot.mark_method,
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
                for snapshot, instrument in rows
            )
        )

    def list_latest_underlying_market(
        self, *, symbols: Sequence[str] | None = None
    ) -> tuple[dict[str, Any], ...]:
        normalized = _normalized_symbols(symbols)
        if symbols is not None and not normalized:
            return ()
        instrument_ids = self._instrument_ids_for_symbols(normalized)
        if normalized and not instrument_ids:
            return ()
        latest_retrieval_query = (
            select(
                UnderlyingMarketSnapshotTable.instrument_id,
                func.max(RawMarketEventTable.observed_at).label("latest_at"),
            )
            .join(
                RawMarketEventTable,
                RawMarketEventTable.id == UnderlyingMarketSnapshotTable.raw_event_id,
            )
            .group_by(UnderlyingMarketSnapshotTable.instrument_id)
        )
        if instrument_ids is not None:
            latest_retrieval_query = latest_retrieval_query.where(
                UnderlyingMarketSnapshotTable.instrument_id.in_(instrument_ids)
            )
        latest_retrieval = latest_retrieval_query.subquery()
        ranked_query = (
            select(
                UnderlyingMarketSnapshotTable.id.label("snapshot_id"),
                func.row_number()
                .over(
                    partition_by=UnderlyingMarketSnapshotTable.instrument_id,
                    order_by=(
                        RawMarketEventTable.observed_at.desc(),
                        RawMarketEventTable.created_at.desc(),
                        UnderlyingMarketSnapshotTable.created_at.desc(),
                        UnderlyingMarketSnapshotTable.raw_event_id.desc(),
                        UnderlyingMarketSnapshotTable.id.desc(),
                    ),
                )
                .label("version_rank"),
            )
            .join(
                RawMarketEventTable,
                RawMarketEventTable.id == UnderlyingMarketSnapshotTable.raw_event_id,
            )
            .join(
                latest_retrieval,
                and_(
                    latest_retrieval.c.instrument_id == UnderlyingMarketSnapshotTable.instrument_id,
                    latest_retrieval.c.latest_at == RawMarketEventTable.observed_at,
                ),
            )
        )
        ranked = ranked_query.subquery()
        with self._session_factory() as session:
            query = (
                select(UnderlyingMarketSnapshotTable, InstrumentTable)
                .join(
                    InstrumentTable,
                    InstrumentTable.id == UnderlyingMarketSnapshotTable.instrument_id,
                )
                .join(
                    ranked,
                    ranked.c.snapshot_id == UnderlyingMarketSnapshotTable.id,
                )
                .where(ranked.c.version_rank == 1)
            )
            if normalized:
                query = query.where(InstrumentTable.symbol.in_(normalized))
            rows = session.execute(query).all()
        return tuple(
            {
                "symbol": instrument.symbol,
                "observed_at": snapshot.observed_at,
                "quote_quality": snapshot.quote_quality,
                "mark_method": snapshot.mark_method,
                "bid": snapshot.bid,
                "ask": snapshot.ask,
                "last": snapshot.last,
                "mark": snapshot.mark,
                "previous_close": snapshot.previous_close,
            }
            for snapshot, instrument in rows
        )

    def list_daily_bars(
        self, *, symbols: Sequence[str] | None = None
    ) -> tuple[dict[str, Any], ...]:
        normalized = _normalized_symbols(symbols)
        if symbols is not None and not normalized:
            return ()
        instrument_ids = self._instrument_ids_for_symbols(normalized)
        if normalized and not instrument_ids:
            return ()
        latest_retrieval_query = (
            select(
                UnderlyingDailyBarTable.instrument_id,
                UnderlyingDailyBarTable.trade_date,
                func.max(RawMarketEventTable.observed_at).label("latest_at"),
            )
            .join(
                RawMarketEventTable,
                RawMarketEventTable.id == UnderlyingDailyBarTable.raw_event_id,
            )
            .group_by(
                UnderlyingDailyBarTable.instrument_id,
                UnderlyingDailyBarTable.trade_date,
            )
        )
        if instrument_ids is not None:
            latest_retrieval_query = latest_retrieval_query.where(
                UnderlyingDailyBarTable.instrument_id.in_(instrument_ids)
            )
        latest_retrieval = latest_retrieval_query.subquery()
        ranked_query = (
            select(
                UnderlyingDailyBarTable.id.label("bar_id"),
                func.row_number()
                .over(
                    partition_by=(
                        UnderlyingDailyBarTable.instrument_id,
                        UnderlyingDailyBarTable.trade_date,
                    ),
                    order_by=(
                        RawMarketEventTable.observed_at.desc(),
                        RawMarketEventTable.created_at.desc(),
                        UnderlyingDailyBarTable.created_at.desc(),
                        UnderlyingDailyBarTable.raw_event_id.desc(),
                        UnderlyingDailyBarTable.id.desc(),
                    ),
                )
                .label("version_rank"),
            )
            .join(
                RawMarketEventTable,
                RawMarketEventTable.id == UnderlyingDailyBarTable.raw_event_id,
            )
            .join(
                latest_retrieval,
                and_(
                    latest_retrieval.c.instrument_id == UnderlyingDailyBarTable.instrument_id,
                    latest_retrieval.c.trade_date == UnderlyingDailyBarTable.trade_date,
                    latest_retrieval.c.latest_at == RawMarketEventTable.observed_at,
                ),
            )
        )
        ranked = ranked_query.subquery()
        with self._session_factory() as session:
            query = (
                select(UnderlyingDailyBarTable, InstrumentTable)
                .join(InstrumentTable, InstrumentTable.id == UnderlyingDailyBarTable.instrument_id)
                .join(
                    ranked,
                    ranked.c.bar_id == UnderlyingDailyBarTable.id,
                )
                .where(ranked.c.version_rank == 1)
                .order_by(InstrumentTable.symbol, UnderlyingDailyBarTable.trade_date)
            )
            if normalized:
                query = query.where(InstrumentTable.symbol.in_(normalized))
            rows = session.execute(query).all()
        return tuple(
            {
                "symbol": instrument.symbol,
                "trade_date": bar.trade_date,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar, instrument in rows
        )

    def list_intraday_bars(
        self, *, symbols: Sequence[str] | None = None
    ) -> tuple[dict[str, Any], ...]:
        normalized = _normalized_symbols(symbols)
        if symbols is not None and not normalized:
            return ()
        instrument_ids = self._instrument_ids_for_symbols(normalized)
        if normalized and not instrument_ids:
            return ()
        ranked_query = select(
            UnderlyingIntradayBarTable.id.label("bar_id"),
            func.row_number()
            .over(
                partition_by=(
                    UnderlyingIntradayBarTable.instrument_id,
                    UnderlyingIntradayBarTable.started_at,
                    UnderlyingIntradayBarTable.interval_minutes,
                ),
                order_by=(
                    RawMarketEventTable.observed_at.desc(),
                    RawMarketEventTable.created_at.desc(),
                    UnderlyingIntradayBarTable.created_at.desc(),
                    UnderlyingIntradayBarTable.id.desc(),
                ),
            )
            .label("version_rank"),
        ).join(
            RawMarketEventTable,
            RawMarketEventTable.id == UnderlyingIntradayBarTable.raw_event_id,
        )
        if instrument_ids is not None:
            ranked_query = ranked_query.where(
                UnderlyingIntradayBarTable.instrument_id.in_(instrument_ids)
            )
        ranked = ranked_query.subquery()
        with self._session_factory() as session:
            query = (
                select(UnderlyingIntradayBarTable, InstrumentTable)
                .join(
                    InstrumentTable,
                    InstrumentTable.id == UnderlyingIntradayBarTable.instrument_id,
                )
                .join(ranked, ranked.c.bar_id == UnderlyingIntradayBarTable.id)
                .where(ranked.c.version_rank == 1)
                .order_by(InstrumentTable.symbol, UnderlyingIntradayBarTable.started_at)
            )
            if normalized:
                query = query.where(InstrumentTable.symbol.in_(normalized))
            rows = session.execute(query).all()
        return tuple(
            {
                "symbol": instrument.symbol,
                "started_at": bar.started_at,
                "interval_minutes": bar.interval_minutes,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar, instrument in rows
        )

    def _instrument_ids_for_symbols(self, symbols: tuple[str, ...]) -> tuple[str, ...] | None:
        if not symbols:
            return None
        with self._session_factory() as session:
            return tuple(
                session.scalars(
                    select(InstrumentTable.id).where(InstrumentTable.symbol.in_(symbols))
                ).all()
            )

    def _instrument_ids_for_option_market(
        self,
        *,
        symbols: tuple[str, ...],
        underlyings: tuple[str, ...],
        expiration_on_or_after: date | None,
        unbounded: bool,
    ) -> tuple[str, ...] | None:
        if unbounded:
            return None
        conditions: list[ColumnElement[bool]] = []
        if symbols:
            conditions.append(InstrumentTable.symbol.in_(symbols))
        if underlyings:
            chain: list[ColumnElement[bool]] = [InstrumentTable.underlying_symbol.in_(underlyings)]
            if expiration_on_or_after is not None:
                chain.append(InstrumentTable.expiration_date >= expiration_on_or_after)
            conditions.append(and_(*chain))
        if not conditions:
            return ()
        with self._session_factory() as session:
            return tuple(session.scalars(select(InstrumentTable.id).where(or_(*conditions))).all())


def _instrument_values(
    instrument: InstrumentTable,
    canonical: dict[str, tuple[Any, bool]] | None = None,
) -> dict[str, Any]:
    multiplier, is_non_standard = _instrument_option_metadata(instrument, canonical or {})
    return {
        "instrument_external_key": instrument.external_key,
        "symbol": instrument.symbol,
        "asset_type": instrument.asset_type,
        "description": instrument.description,
        "underlying_symbol": instrument.underlying_symbol,
        "option_side": instrument.option_side,
        "expiration_date": instrument.expiration_date,
        "strike": instrument.strike,
        "contract_multiplier": multiplier,
        "is_non_standard": is_non_standard,
        "deliverable": instrument.deliverable,
    }


def _normalized_symbols(symbols: Sequence[str] | None) -> tuple[str, ...]:
    if symbols is None:
        return ()
    return tuple(
        sorted({symbol.strip().upper() for symbol in symbols if symbol and symbol.strip()})
    )


def _observed_at(row: dict[str, Any]) -> datetime:
    value = row.get("observed_at")
    if not isinstance(value, datetime):
        return datetime.min.replace(tzinfo=UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _dedupe_option_market_rows(
    rows: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = "".join(str(row.get("symbol") or "").upper().split())
        if not key:
            key = f"{row.get('underlying_symbol')}:{row.get('expiration_date')}:{row.get('strike')}"
        current = best.get(key)
        if current is None or _observed_at(row) > _observed_at(current):
            best[key] = row
    return tuple(best[key] for key in sorted(best))


def _canonical_option_metadata(
    session: Any,
) -> dict[str, tuple[Any, bool]]:
    """Resolve contract terms only when chain observations agree by OCC symbol.

    Schwab's account-position payload omits multiplier and standardness, while
    its option-chain payload supplies both under a separate instrument key. A
    canonical OCC-symbol join is safe only when every explicit chain record
    agrees; conflicting or unknown deliverables remain unresolved.
    """

    candidates: dict[str, set[tuple[Any, bool]]] = {}
    rows = session.execute(
        select(
            InstrumentTable.symbol,
            InstrumentTable.contract_multiplier,
            InstrumentTable.deliverable,
        ).where(
            InstrumentTable.asset_type == "option",
            InstrumentTable.contract_multiplier.is_not(None),
        )
    )
    for symbol, multiplier, deliverable in rows:
        if not isinstance(deliverable, dict):
            continue
        kind = str(deliverable.get("kind") or "").casefold()
        if kind not in {"standard", "adjusted"}:
            continue
        key = "".join(str(symbol).upper().split())
        candidates.setdefault(key, set()).add((multiplier, kind == "adjusted"))
    return {symbol: next(iter(values)) for symbol, values in candidates.items() if len(values) == 1}


def _position_option_metadata(
    position: Any,
    instrument: InstrumentTable | None,
    canonical: dict[str, tuple[Any, bool]],
) -> tuple[Any, bool | None]:
    if str(position.asset_type).upper() != "OPTION":
        return position.contract_multiplier, position.is_non_standard
    fallback = canonical.get("".join(str(position.symbol).upper().split()))
    multiplier = position.contract_multiplier
    if multiplier is None and instrument is not None:
        multiplier = instrument.contract_multiplier
    if multiplier is None and fallback is not None:
        multiplier = fallback[0]

    standardness = position.is_non_standard
    if standardness is None and instrument is not None and isinstance(instrument.deliverable, dict):
        kind = str(instrument.deliverable.get("kind") or "").casefold()
        if kind in {"standard", "adjusted"}:
            standardness = kind == "adjusted"
    if standardness is None and fallback is not None:
        standardness = fallback[1]
    return multiplier, standardness


def _instrument_option_metadata(
    instrument: InstrumentTable,
    canonical: dict[str, tuple[Any, bool]],
) -> tuple[Any, bool | None]:
    if str(instrument.asset_type).upper() != "OPTION":
        return instrument.contract_multiplier, None
    fallback = canonical.get("".join(str(instrument.symbol).upper().split()))
    multiplier = instrument.contract_multiplier
    if multiplier is None and fallback is not None:
        multiplier = fallback[0]

    standardness = None
    if isinstance(instrument.deliverable, dict):
        kind = str(instrument.deliverable.get("kind") or "").casefold()
        if kind in {"standard", "adjusted"}:
            standardness = kind == "adjusted"
    if standardness is None and fallback is not None:
        standardness = fallback[1]
    return multiplier, standardness
