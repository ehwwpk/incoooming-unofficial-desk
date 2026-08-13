from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import delete, select

from schwab_dashboard.domain.opportunity import RadarMode, RadarPolicy, RadarProjection
from schwab_dashboard.infrastructure.database.engine import SessionFactory
from schwab_dashboard.infrastructure.database.tables.opportunity import (
    RadarCandidateSnapshotTable,
    RadarLookupRunTable,
    RadarPolicyTable,
    RadarSavedSymbolTable,
)


class SqlOpportunityStore:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def load_policy(self, *, symbol: str, mode: RadarMode) -> RadarPolicy | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(RadarPolicyTable).where(
                    RadarPolicyTable.symbol == symbol,
                    RadarPolicyTable.mode == mode.value,
                )
            )
        return _policy_from_row(row) if row is not None else None

    def save_policy(self, policy: RadarPolicy) -> RadarPolicy:
        with self._session_factory() as session:
            row = session.scalar(
                select(RadarPolicyTable).where(
                    RadarPolicyTable.symbol == policy.symbol,
                    RadarPolicyTable.mode == policy.mode.value,
                )
            )
            now = datetime.now(UTC)
            if row is None:
                row = RadarPolicyTable(symbol=policy.symbol, mode=policy.mode.value)
                session.add(row)
                next_version = 1
            else:
                next_version = row.version + 1
            _apply_policy(row, policy, version=next_version, updated_at=now)
            session.commit()
            session.refresh(row)
            return _policy_from_row(row)

    def create_lookup(
        self,
        *,
        symbol: str,
        mode: RadarMode,
        source: str,
        requested_at: datetime,
    ) -> str:
        row = RadarLookupRunTable(
            source=source,
            symbol=symbol,
            mode=mode.value,
            state="fetching",
            requested_at=requested_at,
        )
        with self._session_factory() as session:
            session.add(row)
            session.commit()
            return row.id

    def complete_lookup(self, projection: RadarProjection, *, completed_at: datetime) -> None:
        if projection.lookup_id is None:
            raise ValueError("completed Radar projection must have a lookup_id")
        payload = _jsonable(asdict(projection))
        with self._session_factory() as session:
            row = session.get(RadarLookupRunTable, projection.lookup_id)
            if row is None:
                raise LookupError(f"Radar lookup not found: {projection.lookup_id}")
            row.state = projection.state.value
            row.completed_at = completed_at
            row.observed_at = projection.observed_at
            row.policy_version = projection.policy.version
            row.projection = payload
            row.error_message = None
            for candidate in projection.candidates:
                candidate_payload = _jsonable(asdict(candidate))
                session.add(
                    RadarCandidateSnapshotTable(
                        lookup_id=projection.lookup_id,
                        option_symbol=candidate.option_symbol,
                        frontier_label=(
                            candidate.label.value if candidate.label is not None else None
                        ),
                        metrics={
                            key: value
                            for key, value in candidate_payload.items()
                            if key not in {"gates", "reasons"}
                        },
                        gates=candidate_payload["gates"],
                    )
                )
            session.commit()

    def fail_lookup(
        self,
        lookup_id: str,
        *,
        state: str,
        error_message: str,
        completed_at: datetime,
    ) -> None:
        with self._session_factory() as session:
            row = session.get(RadarLookupRunTable, lookup_id)
            if row is None:
                return
            row.state = state
            row.completed_at = completed_at
            row.error_message = error_message[:512]
            session.commit()

    def load_lookup(self, lookup_id: str) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.get(RadarLookupRunTable, lookup_id)
            if row is None:
                return None
            return {
                "lookup_id": row.id,
                "source": row.source,
                "symbol": row.symbol,
                "mode": row.mode,
                "state": row.state,
                "requested_at": row.requested_at,
                "completed_at": row.completed_at,
                "observed_at": row.observed_at,
                "policy_version": row.policy_version,
                "projection": row.projection,
                "error_message": row.error_message,
            }

    def list_saved_symbols(self, *, source: str) -> tuple[str, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(RadarSavedSymbolTable)
                .where(RadarSavedSymbolTable.source == source)
                .order_by(RadarSavedSymbolTable.symbol)
            ).all()
        return tuple(row.symbol for row in rows)

    def save_symbol(self, *, symbol: str, source: str, saved_at: datetime) -> None:
        with self._session_factory() as session:
            row = session.scalar(
                select(RadarSavedSymbolTable).where(
                    RadarSavedSymbolTable.source == source,
                    RadarSavedSymbolTable.symbol == symbol,
                )
            )
            if row is None:
                session.add(
                    RadarSavedSymbolTable(source=source, symbol=symbol, saved_at=saved_at)
                )
                session.commit()

    def remove_symbol(self, *, symbol: str, source: str) -> None:
        with self._session_factory() as session:
            session.execute(
                delete(RadarSavedSymbolTable).where(
                    RadarSavedSymbolTable.source == source,
                    RadarSavedSymbolTable.symbol == symbol,
                )
            )
            session.commit()


def _policy_from_row(row: RadarPolicyTable) -> RadarPolicy:
    return RadarPolicy(
        symbol=row.symbol,
        mode=RadarMode(row.mode),
        version=row.version,
        minimum_dte=row.minimum_dte,
        maximum_dte=row.maximum_dte,
        minimum_annualized_rate_percent=row.minimum_annualized_rate_percent,
        minimum_strike=row.minimum_strike,
        minimum_strike_distance_percent=row.minimum_strike_distance_percent,
        maximum_effective_entry=row.maximum_effective_entry,
        maximum_spread_percent=row.maximum_spread_percent,
        minimum_open_interest=row.minimum_open_interest,
        minimum_volume=row.minimum_volume,
        maximum_quote_age_seconds=row.maximum_quote_age_seconds,
        allowed_contracts=row.allowed_contracts,
        reserved_cash=row.reserved_cash,
        maximum_five_day_move_percent=row.maximum_five_day_move_percent,
    )


def _apply_policy(
    row: RadarPolicyTable,
    policy: RadarPolicy,
    *,
    version: int,
    updated_at: datetime,
) -> None:
    row.version = version
    row.minimum_dte = policy.minimum_dte
    row.maximum_dte = policy.maximum_dte
    row.minimum_annualized_rate_percent = policy.minimum_annualized_rate_percent
    row.minimum_strike = policy.minimum_strike
    row.minimum_strike_distance_percent = policy.minimum_strike_distance_percent
    row.maximum_effective_entry = policy.maximum_effective_entry
    row.maximum_spread_percent = policy.maximum_spread_percent
    row.minimum_open_interest = policy.minimum_open_interest
    row.minimum_volume = policy.minimum_volume
    row.maximum_quote_age_seconds = policy.maximum_quote_age_seconds
    row.allowed_contracts = policy.allowed_contracts
    row.reserved_cash = policy.reserved_cash
    row.maximum_five_day_move_percent = policy.maximum_five_day_move_percent
    row.updated_at = updated_at


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=_json_default))


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime, Decimal, Enum)):
        return str(value.value) if isinstance(value, Enum) else str(value)
    raise TypeError(f"Unsupported Radar JSON value: {type(value).__name__}")
