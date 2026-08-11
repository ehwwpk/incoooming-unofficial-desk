from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, select

from schwab_dashboard.infrastructure.database.engine import SessionFactory
from schwab_dashboard.infrastructure.database.tables.account import AccountTable
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
    UnderlyingMarketSnapshotTable,
)


class SqlLiveAnalyticsReader:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def list_executions(self) -> tuple[dict[str, Any], ...]:
        with self._session_factory() as session:
            rows = session.execute(
                select(ExecutionTable, InstrumentTable, AccountTable)
                .join(InstrumentTable, InstrumentTable.id == ExecutionTable.instrument_id)
                .join(AccountTable, AccountTable.id == ExecutionTable.account_id)
                .order_by(ExecutionTable.occurred_at)
            ).all()
        return tuple(
            {
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
                **_instrument_values(instrument),
            }
            for execution, instrument, account in rows
        )

    def list_cash_movements(self) -> tuple[dict[str, Any], ...]:
        with self._session_factory() as session:
            rows = session.execute(
                select(CashMovementTable, InstrumentTable, AccountTable)
                .outerjoin(InstrumentTable, InstrumentTable.id == CashMovementTable.instrument_id)
                .join(AccountTable, AccountTable.id == CashMovementTable.account_id)
                .order_by(CashMovementTable.occurred_at)
            ).all()
        return tuple(
            {
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
        with self._session_factory() as session:
            rows = session.execute(
                select(OptionLifecycleEventTable, InstrumentTable, AccountTable)
                .join(
                    InstrumentTable,
                    InstrumentTable.id == OptionLifecycleEventTable.option_instrument_id,
                )
                .join(AccountTable, AccountTable.id == OptionLifecycleEventTable.account_id)
                .order_by(OptionLifecycleEventTable.occurred_at)
            ).all()
        return tuple(
            {
                "external_key": event.external_key,
                "occurred_at": event.occurred_at,
                "event_type": event.event_type,
                "option_quantity": event.option_quantity,
                "stock_quantity": event.stock_quantity,
                "cash_amount": event.cash_amount,
                "details": event.details,
                "account_mask": account.account_mask,
                **_instrument_values(instrument),
            }
            for event, instrument, account in rows
        )

    def list_latest_option_market(self) -> tuple[dict[str, Any], ...]:
        latest = (
            select(
                OptionMarketSnapshotTable.instrument_id,
                func.max(RawMarketEventTable.observed_at).label("latest_at"),
            )
            .join(
                RawMarketEventTable,
                RawMarketEventTable.id == OptionMarketSnapshotTable.raw_event_id,
            )
            .group_by(OptionMarketSnapshotTable.instrument_id)
            .subquery()
        )
        with self._session_factory() as session:
            rows = session.execute(
                select(OptionMarketSnapshotTable, InstrumentTable)
                .join(
                    InstrumentTable,
                    InstrumentTable.id == OptionMarketSnapshotTable.instrument_id,
                )
                .join(
                    RawMarketEventTable,
                    RawMarketEventTable.id == OptionMarketSnapshotTable.raw_event_id,
                )
                .join(
                    latest,
                    and_(
                        latest.c.instrument_id == OptionMarketSnapshotTable.instrument_id,
                        latest.c.latest_at == RawMarketEventTable.observed_at,
                    ),
                )
            ).all()
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

    def list_latest_underlying_market(self) -> tuple[dict[str, Any], ...]:
        latest = (
            select(
                UnderlyingMarketSnapshotTable.instrument_id,
                func.max(RawMarketEventTable.observed_at).label("latest_at"),
            )
            .join(
                RawMarketEventTable,
                RawMarketEventTable.id == UnderlyingMarketSnapshotTable.raw_event_id,
            )
            .group_by(UnderlyingMarketSnapshotTable.instrument_id)
            .subquery()
        )
        with self._session_factory() as session:
            rows = session.execute(
                select(UnderlyingMarketSnapshotTable, InstrumentTable)
                .join(
                    InstrumentTable,
                    InstrumentTable.id == UnderlyingMarketSnapshotTable.instrument_id,
                )
                .join(
                    RawMarketEventTable,
                    RawMarketEventTable.id == UnderlyingMarketSnapshotTable.raw_event_id,
                )
                .join(
                    latest,
                    and_(
                        latest.c.instrument_id == UnderlyingMarketSnapshotTable.instrument_id,
                        latest.c.latest_at == RawMarketEventTable.observed_at,
                    ),
                )
            ).all()
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

    def list_daily_bars(self) -> tuple[dict[str, Any], ...]:
        latest = (
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
            .subquery()
        )
        with self._session_factory() as session:
            rows = session.execute(
                select(UnderlyingDailyBarTable, InstrumentTable)
                .join(InstrumentTable, InstrumentTable.id == UnderlyingDailyBarTable.instrument_id)
                .join(
                    RawMarketEventTable,
                    RawMarketEventTable.id == UnderlyingDailyBarTable.raw_event_id,
                )
                .join(
                    latest,
                    and_(
                        latest.c.instrument_id == UnderlyingDailyBarTable.instrument_id,
                        latest.c.trade_date == UnderlyingDailyBarTable.trade_date,
                        latest.c.latest_at == RawMarketEventTable.observed_at,
                    ),
                )
                .order_by(InstrumentTable.symbol, UnderlyingDailyBarTable.trade_date)
            ).all()
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


def _instrument_values(instrument: InstrumentTable) -> dict[str, Any]:
    return {
        "instrument_external_key": instrument.external_key,
        "symbol": instrument.symbol,
        "asset_type": instrument.asset_type,
        "description": instrument.description,
        "underlying_symbol": instrument.underlying_symbol,
        "option_side": instrument.option_side,
        "expiration_date": instrument.expiration_date,
        "strike": instrument.strike,
        "contract_multiplier": instrument.contract_multiplier,
    }
