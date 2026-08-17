from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from schwab_dashboard.application.ports.repositories import (
    AccountBalanceSnapshotWrite,
    PositionSnapshotWrite,
)
from schwab_dashboard.domain.broker import BrokerAccount
from schwab_dashboard.infrastructure.database.tables.account import (
    AccountBalanceSnapshotTable,
    AccountTable,
    PositionSnapshotTable,
)
from schwab_dashboard.infrastructure.database.tables.sync import SyncRunTable

NON_MARKET_ASSET_TYPES = ("OPTION", "CASH", "FIXED_INCOME", "CURRENCY")


class SqlAccountRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(self, account: BrokerAccount, *, observed_at: datetime) -> str:
        row = self._session.scalar(
            select(AccountTable).where(
                AccountTable.source == "schwab",
                AccountTable.external_account_key == account.external_key,
            )
        )
        if row is None:
            row = AccountTable(
                source="schwab",
                external_account_key=account.external_key,
                account_mask=account.account_mask,
                account_type=account.account_type,
                first_observed_at=observed_at,
                last_observed_at=observed_at,
            )
            self._session.add(row)
        else:
            row.account_mask = account.account_mask
            row.account_type = account.account_type
            row.last_observed_at = observed_at
        self._session.flush()
        return row.id

    def list_summaries(self) -> Sequence[dict[str, Any]]:
        rows = self._session.scalars(select(AccountTable).order_by(AccountTable.account_mask)).all()
        return [
            {
                "id": row.id,
                "account_mask": row.account_mask,
                "account_type": row.account_type,
                "first_observed_at": row.first_observed_at,
                "last_observed_at": row.last_observed_at,
            }
            for row in rows
        ]

    def require_id(self, *, source: str, external_account_key: str) -> str:
        account_id = self._session.scalar(
            select(AccountTable.id).where(
                AccountTable.source == source,
                AccountTable.external_account_key == external_account_key,
            )
        )
        if account_id is None:
            raise LookupError(
                f"Account {external_account_key!r} from source {source!r} does not exist"
            )
        return account_id


class SqlPositionSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, snapshot: PositionSnapshotWrite) -> str:
        row = PositionSnapshotTable(
            account_id=snapshot.account_id,
            sync_run_id=snapshot.sync_run_id,
            raw_event_id=snapshot.raw_event_id,
            observed_at=snapshot.observed_at,
            instrument_key=snapshot.instrument_key,
            symbol=snapshot.symbol,
            asset_type=snapshot.asset_type,
            long_quantity=snapshot.long_quantity,
            short_quantity=snapshot.short_quantity,
            average_price=snapshot.average_price,
            market_value=snapshot.market_value,
            day_profit_loss=snapshot.day_profit_loss,
            day_profit_loss_percent=snapshot.day_profit_loss_percent,
            description=snapshot.description,
            underlying_symbol=snapshot.underlying_symbol,
            option_type=snapshot.option_type,
            expiration_date=snapshot.expiration_date,
            strike=snapshot.strike,
            long_open_profit_loss=snapshot.long_open_profit_loss,
            short_open_profit_loss=snapshot.short_open_profit_loss,
        )
        self._session.add(row)
        self._session.flush()
        return row.id

    def list_recent_market_symbols(self, *, since: datetime) -> Sequence[str]:
        """Tradable symbols seen in any snapshot since a cutoff, held or not.

        A counterfactual that freezes the book keeps holding a position after
        the real account exits it, so its daily closes must keep arriving. Only
        the latest snapshot drives quotes and chains; this wider set exists so
        price history does not stop the day a position is closed.
        """

        rows = self._session.execute(
            select(PositionSnapshotTable.symbol)
            .where(
                PositionSnapshotTable.observed_at >= since,
                PositionSnapshotTable.asset_type.notin_(NON_MARKET_ASSET_TYPES),
            )
            .distinct()
        ).scalars()
        return sorted({symbol.strip().upper() for symbol in rows if symbol and symbol.strip()})

    def list_latest(self) -> Sequence[dict[str, Any]]:
        latest_run_id = self._session.scalar(
            select(PositionSnapshotTable.sync_run_id)
            .join(SyncRunTable, SyncRunTable.id == PositionSnapshotTable.sync_run_id)
            .where(SyncRunTable.status == "completed")
            .order_by(PositionSnapshotTable.observed_at.desc())
            .limit(1)
        )
        if latest_run_id is None:
            return []

        rows = self._session.execute(
            select(PositionSnapshotTable, AccountTable)
            .join(AccountTable, PositionSnapshotTable.account_id == AccountTable.id)
            .where(PositionSnapshotTable.sync_run_id == latest_run_id)
            .order_by(AccountTable.account_mask, PositionSnapshotTable.symbol)
        ).all()
        return [
            {
                "account_mask": account.account_mask,
                "symbol": position.symbol,
                "asset_type": position.asset_type,
                "long_quantity": position.long_quantity,
                "short_quantity": position.short_quantity,
                "net_quantity": position.long_quantity - position.short_quantity,
                "average_price": position.average_price,
                "market_value": position.market_value,
                "day_profit_loss": position.day_profit_loss,
                "day_profit_loss_percent": position.day_profit_loss_percent,
                "description": position.description,
                "underlying_symbol": position.underlying_symbol,
                "option_type": position.option_type,
                "expiration_date": position.expiration_date,
                "strike": position.strike,
                "long_open_profit_loss": position.long_open_profit_loss,
                "short_open_profit_loss": position.short_open_profit_loss,
                "observed_at": position.observed_at,
            }
            for position, account in rows
        ]


class SqlAccountBalanceSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, snapshot: AccountBalanceSnapshotWrite) -> str:
        row = AccountBalanceSnapshotTable(**asdict(snapshot))
        self._session.add(row)
        self._session.flush()
        return row.id

    def list_latest(self) -> Sequence[dict[str, Any]]:
        latest_run_id = self._session.scalar(
            select(AccountBalanceSnapshotTable.sync_run_id)
            .join(SyncRunTable, SyncRunTable.id == AccountBalanceSnapshotTable.sync_run_id)
            .where(SyncRunTable.status == "completed")
            .order_by(AccountBalanceSnapshotTable.observed_at.desc())
            .limit(1)
        )
        if latest_run_id is None:
            return []
        rows = self._session.execute(
            select(AccountBalanceSnapshotTable, AccountTable)
            .join(AccountTable, AccountBalanceSnapshotTable.account_id == AccountTable.id)
            .where(AccountBalanceSnapshotTable.sync_run_id == latest_run_id)
            .order_by(AccountTable.account_mask)
        ).all()
        return [
            {
                "account_mask": account.account_mask,
                "liquidation_value": row.liquidation_value,
                "initial_liquidation_value": row.initial_liquidation_value,
                "equity": row.equity,
                "cash_balance": row.cash_balance,
                "money_market_fund": row.money_market_fund,
                "margin_balance": row.margin_balance,
                "buying_power": row.buying_power,
                "available_funds": row.available_funds,
                "maintenance_requirement": row.maintenance_requirement,
                "long_market_value": row.long_market_value,
                "short_market_value": row.short_market_value,
                "long_option_market_value": row.long_option_market_value,
                "short_option_market_value": row.short_option_market_value,
                "is_portfolio_margin": row.is_portfolio_margin,
                "is_intraday_margin": row.is_intraday_margin,
                "observed_at": row.observed_at,
            }
            for row, account in rows
        ]
