from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime
from threading import RLock
from typing import Any
from uuid import uuid4

from schwab_dashboard.domain.opportunity import RadarMode, RadarPolicy, RadarProjection


class DemoOpportunityStore:
    """Keep fictional Radar activity in this session, outside the live ledger."""

    def __init__(self) -> None:
        self._policies: dict[tuple[str, RadarMode], RadarPolicy] = {}
        self._lookups: dict[str, dict[str, Any]] = {}
        self._symbols: set[tuple[str, str]] = set()
        self._lock = RLock()

    def load_policy(self, *, symbol: str, mode: RadarMode) -> RadarPolicy | None:
        with self._lock:
            return self._policies.get((symbol, mode))

    def save_policy(self, policy: RadarPolicy) -> RadarPolicy:
        with self._lock:
            key = (policy.symbol, policy.mode)
            previous = self._policies.get(key)
            saved = replace(policy, version=previous.version + 1 if previous else 1)
            self._policies[key] = saved
            return saved

    def create_lookup(
        self, *, symbol: str, mode: RadarMode, source: str, requested_at: datetime
    ) -> str:
        with self._lock:
            lookup_id = str(uuid4())
            self._lookups[lookup_id] = {
                "lookup_id": lookup_id,
                "source": source,
                "symbol": symbol,
                "mode": mode.value,
                "state": "fetching",
                "requested_at": requested_at,
                "completed_at": None,
                "observed_at": None,
                "policy_version": None,
                "projection": None,
                "error_message": None,
            }
            return lookup_id

    def complete_lookup(self, projection: RadarProjection, *, completed_at: datetime) -> None:
        with self._lock:
            if projection.lookup_id not in self._lookups:
                raise LookupError("Demo Radar lookup not found")
            self._lookups[projection.lookup_id].update(
                state=projection.state.value,
                completed_at=completed_at,
                observed_at=projection.observed_at,
                policy_version=projection.policy.version,
                projection=asdict(projection),
                error_message=None,
            )

    def fail_lookup(
        self, lookup_id: str, *, state: str, error_message: str, completed_at: datetime
    ) -> None:
        with self._lock:
            if lookup_id in self._lookups:
                self._lookups[lookup_id].update(
                    state=state, error_message=error_message[:512], completed_at=completed_at
                )

    def load_lookup(self, lookup_id: str) -> dict[str, Any] | None:
        with self._lock:
            return deepcopy(self._lookups.get(lookup_id))

    def list_saved_symbols(self, *, source: str) -> tuple[str, ...]:
        with self._lock:
            return tuple(
                sorted(symbol for item_source, symbol in self._symbols if item_source == source)
            )

    def save_symbol(self, *, symbol: str, source: str, saved_at: datetime) -> None:
        del saved_at
        with self._lock:
            self._symbols.add((source, symbol))

    def remove_symbol(self, *, symbol: str, source: str) -> None:
        with self._lock:
            self._symbols.discard((source, symbol))
