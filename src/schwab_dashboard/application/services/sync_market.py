from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise

from schwab_dashboard.application.errors import BrokerPayloadError, BrokerRequestError
from schwab_dashboard.application.market_time import market_date
from schwab_dashboard.application.performance.sessions import build_market_calendar
from schwab_dashboard.application.ports.analytics import LiveAnalyticsReader
from schwab_dashboard.application.ports.repositories import UnitOfWorkFactory
from schwab_dashboard.application.services.market_history_refresh import (
    MarketHistoryRefreshPolicy,
)
from schwab_dashboard.application.services.record_market_observations import (
    RecordMarketObservations,
)
from schwab_dashboard.domain.instruments import AssetType
from schwab_dashboard.infrastructure.schwab.gateway import SchwabReadOnlyMarketDataClient
from schwab_dashboard.infrastructure.schwab.market_mapper import SchwabMarketMapper

MARKET_REFERENCE_SYMBOLS = frozenset({"SPY"})
INTRADAY_LOOKBACK = timedelta(days=60)
# Closed positions keep costing one throttled history call each, so the
# counterfactual's reach is deliberately bounded rather than unbounded.
EXITED_HISTORY_LOOKBACK = timedelta(days=120)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MarketSyncResult:
    underlying_quote_count: int
    option_quote_count: int
    daily_bar_count: int
    completed_at: datetime
    intraday_bar_count: int = 0


class SyncSchwabMarketData:
    def __init__(
        self,
        *,
        client: SchwabReadOnlyMarketDataClient,
        mapper: SchwabMarketMapper,
        recorder: RecordMarketObservations,
        uow_factory: UnitOfWorkFactory,
        parser_version: str,
        history_refresh_policy: MarketHistoryRefreshPolicy | None = None,
        analytics_reader: LiveAnalyticsReader | None = None,
    ) -> None:
        self._client = client
        self._mapper = mapper
        self._recorder = recorder
        self._uow_factory = uow_factory
        self._parser_version = parser_version
        self._history_refresh_policy = history_refresh_policy
        self._analytics_reader = analytics_reader

    def execute(self) -> MarketSyncResult:
        with self._uow_factory() as uow:
            # A full refresh stages the account child until activity and market
            # both finish. Market selection must read that staged child while
            # user-facing readers continue to see the prior published book.
            positions = tuple(uow.positions.list_latest(include_staged=True))
            balances = tuple(uow.balances.list_latest(include_staged=True))
            recently_held = tuple(
                uow.positions.list_recent_market_symbols(
                    since=datetime.now(UTC) - EXITED_HISTORY_LOOKBACK
                )
            )

        held_assets = _held_market_assets(positions)
        symbols = sorted(held_assets)
        option_positions: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
        for row in positions:
            if str(row.get("asset_type") or "").upper() != "OPTION":
                continue
            if not row.get("short_quantity"):
                continue
            underlying = row.get("underlying_symbol")
            expiration = row.get("expiration_date")
            if underlying and expiration:
                option_positions[str(underlying)].append(dict(row))

        underlying_count = 0
        option_count = 0
        daily_bar_count = 0
        intraday_bar_count = 0
        if symbols:
            quotes = self._client.get_quotes(symbols)
            quote_received_at = datetime.now(UTC)
            quote_result = self._recorder.execute(
                self._mapper.map_quotes(
                    quotes,
                    observed_at=quote_received_at,
                    parser_version=self._parser_version,
                )
            )
            underlying_count += quote_result.underlying_snapshot_count

        for underlying, rows in sorted(option_positions.items()):
            expirations = [_as_date(row["expiration_date"]) for row in rows]
            chain = self._client.get_option_chain(
                underlying,
                from_date=min(expirations),
                to_date=max(expirations) + timedelta(days=56),
                contract_type="ALL",
                strike_count=250,
            )
            chain_received_at = datetime.now(UTC)
            chain_result = self._recorder.execute(
                self._mapper.map_chain(
                    chain,
                    observed_at=chain_received_at,
                    parser_version=self._parser_version,
                )
            )
            option_count += chain_result.option_snapshot_count

        # Daily history is a portfolio input, not merely an option-chain input.
        # Store it for every held market symbol so the frozen-shares baseline can
        # represent the whole book, plus the explicit price-only market reference.
        # Recently exited symbols stay in this set because the frozen-share
        # counterfactual never sold them and still needs their closes.
        for symbol in _history_symbols(symbols, recently_held=recently_held):
            requested_at = datetime.now(UTC)
            if self._history_refresh_policy is not None and not self._history_refresh_policy.is_due(
                symbol,
                now=requested_at,
            ):
                continue
            history = self._client.get_daily_price_history(symbol)
            history_received_at = datetime.now(UTC)
            history_batch = self._mapper.map_price_history(
                history,
                observed_at=history_received_at,
                parser_version=self._parser_version,
                asset_type=held_assets.get(symbol, AssetType.ETF),
            )
            self._recorder.execute(history_batch)
            daily_bar_count += len(history_batch.daily_bars)
            if self._history_refresh_policy is not None:
                self._history_refresh_policy.mark_succeeded(symbol, at=requested_at)

        # Recover option closes only for contracts proven relevant to a missing
        # account-valuation interval. Chain-wide history would be enormous and
        # mostly unrelated to the held book. Failures are non-fatal: the
        # valuation engine will label the affected sessions estimated.
        for symbol in self._required_gap_option_symbols(
            current_positions=positions,
            current_balances=balances,
        ):
            requested_at = datetime.now(UTC)
            policy_key = f"option-history:{symbol}"
            if self._history_refresh_policy is not None and not self._history_refresh_policy.is_due(
                policy_key,
                now=requested_at,
            ):
                continue
            try:
                history = self._client.get_daily_price_history(symbol, end_at=requested_at)
                history_received_at = datetime.now(UTC)
                history_batch = self._mapper.map_price_history(
                    history,
                    observed_at=history_received_at,
                    parser_version=f"{self._parser_version}-option-gap",
                    asset_type=AssetType.OPTION,
                )
                self._recorder.execute(history_batch)
                daily_bar_count += len(history_batch.daily_bars)
            except (BrokerPayloadError, BrokerRequestError, ValueError) as exc:
                logger.warning("Historical option marks unavailable for %s: %s", symbol, exc)
                continue
            if self._history_refresh_policy is not None:
                self._history_refresh_policy.mark_succeeded(policy_key, at=requested_at)

        # Intraday bars are chart enrichment, never a reason to fail the core
        # account refresh. Schwab may constrain minute-history lookbacks per app;
        # retain the verified daily series when that optional request is rejected.
        for symbol in symbols:
            requested_at = datetime.now(UTC)
            policy_key = f"intraday:{symbol}"
            if self._history_refresh_policy is not None and not self._history_refresh_policy.is_due(
                policy_key,
                now=requested_at,
            ):
                continue
            try:
                history = self._client.get_intraday_price_history(
                    symbol,
                    start_at=requested_at - INTRADAY_LOOKBACK,
                    end_at=requested_at,
                    frequency_minutes=30,
                )
                history_received_at = datetime.now(UTC)
                history_batch = self._mapper.map_intraday_price_history(
                    history,
                    observed_at=history_received_at,
                    parser_version=self._parser_version,
                    interval_minutes=30,
                    asset_type=held_assets.get(symbol, AssetType.UNKNOWN),
                )
                self._recorder.execute(history_batch)
                intraday_bar_count += len(history_batch.intraday_bars)
            except (BrokerPayloadError, BrokerRequestError, ValueError) as exc:
                logger.warning("Intraday history unavailable for %s: %s", symbol, exc)
                continue
            if self._history_refresh_policy is not None:
                self._history_refresh_policy.mark_succeeded(policy_key, at=requested_at)

        return MarketSyncResult(
            underlying_quote_count=underlying_count,
            option_quote_count=option_count,
            daily_bar_count=daily_bar_count,
            completed_at=datetime.now(UTC),
            intraday_bar_count=intraday_bar_count,
        )

    def _required_gap_option_symbols(
        self,
        *,
        current_positions: Sequence[Mapping[str, object]] = (),
        current_balances: Sequence[Mapping[str, object]] = (),
    ) -> tuple[str, ...]:
        if self._analytics_reader is None:
            return ()
        balances = tuple(self._analytics_reader.list_balance_history())
        positions = tuple((*self._analytics_reader.list_position_history(), *current_positions))
        executions = tuple(self._analytics_reader.list_executions())
        base_symbols = tuple(
            sorted(
                {
                    str(row.get("symbol") or "").strip().upper()
                    for row in positions
                    if str(row.get("asset_type") or "").upper() != "OPTION"
                }
                | {"SPY"} - {""}
            )
        )
        calendar = build_market_calendar(
            self._analytics_reader.list_daily_bars(symbols=base_symbols)
        )
        observed_days = sorted(
            {
                market_date(row["observed_at"])
                for row in (*balances, *current_balances)
                if isinstance(row.get("observed_at"), (date, datetime))
            }
        )
        gap_intervals = tuple(
            (left, right, calendar.sessions_between(left, right, include_end=False))
            for left, right in pairwise(observed_days)
            if calendar.sessions_between(left, right, include_end=False)
        )
        if not gap_intervals:
            return ()
        required: defaultdict[str, set[date]] = defaultdict(set)
        broker_symbols: dict[str, str] = {}
        snapshots: defaultdict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
        snapshot_order: dict[tuple[str, str], datetime] = {}
        for row in positions:
            observed = row.get("observed_at")
            if not isinstance(observed, datetime):
                continue
            account = str(row.get("account_id") or row.get("account_mask") or "ACCOUNT")
            run = str(row.get("sync_run_id") or observed.isoformat())
            key = (account, run)
            snapshots[key].append(row)
            snapshot_order[key] = max(observed, snapshot_order.get(key, observed))
        for left, right, gap_days in gap_intervals:
            latest_by_account: dict[str, tuple[datetime, tuple[str, str]]] = {}
            for key, observed in snapshot_order.items():
                if market_date(observed) > left:
                    continue
                current = latest_by_account.get(key[0])
                if current is None or observed > current[0]:
                    latest_by_account[key[0]] = (observed, key)
            for _observed, key in latest_by_account.values():
                for row in snapshots[key]:
                    if str(row.get("asset_type") or "").upper() != "OPTION":
                        continue
                    raw_symbol = str(row.get("symbol") or "").strip().upper()
                    symbol = _canonical_symbol(raw_symbol)
                    if not symbol:
                        continue
                    expiration = row.get("expiration_date")
                    required[symbol].update(
                        day
                        for day in gap_days
                        if not isinstance(expiration, date) or day <= _as_date(expiration)
                    )
                    broker_symbols.setdefault(symbol, raw_symbol)
            for row in executions:
                occurred = row.get("occurred_at")
                if (
                    str(row.get("asset_type") or "").upper() != "OPTION"
                    or not isinstance(occurred, (date, datetime))
                    or not left < market_date(occurred) <= right
                ):
                    continue
                raw_symbol = str(row.get("symbol") or "").strip().upper()
                symbol = _canonical_symbol(raw_symbol)
                if not symbol:
                    continue
                expiration = row.get("expiration_date")
                opened = market_date(occurred)
                required[symbol].update(
                    day
                    for day in gap_days
                    if day >= opened
                    and (not isinstance(expiration, date) or day <= _as_date(expiration))
                )
                broker_symbols.setdefault(symbol, raw_symbol)
        api_symbols = tuple(broker_symbols.values())
        existing = self._analytics_reader.list_daily_bars(symbols=api_symbols)
        covered_days: defaultdict[str, set[date]] = defaultdict(set)
        for row in existing:
            symbol = _canonical_symbol(row.get("symbol"))
            if isinstance(row.get("trade_date"), date):
                covered_days[symbol].add(row["trade_date"])
        missing = {
            symbol for symbol, days in required.items() if days and not days <= covered_days[symbol]
        }
        return tuple(sorted(broker_symbols[symbol] for symbol in missing))


def _held_market_assets(
    positions: Sequence[Mapping[str, object]],
) -> dict[str, AssetType]:
    excluded = {"OPTION", "CASH", "FIXED_INCOME"}
    assets: dict[str, AssetType] = {}
    for row in positions:
        raw_type = str(row.get("asset_type") or "").upper()
        symbol = str(row.get("symbol") or "").strip().upper()
        if raw_type in excluded or not symbol:
            continue
        assets[symbol] = _asset_type(raw_type)
    return assets


def _history_symbols(
    held_symbols: list[str],
    *,
    recently_held: Sequence[str] = (),
) -> list[str]:
    return sorted(set(held_symbols) | set(recently_held) | MARKET_REFERENCE_SYMBOLS)


def _asset_type(value: str) -> AssetType:
    normalized = value.strip().upper()
    return {
        "EQUITY": AssetType.EQUITY,
        "ETF": AssetType.ETF,
        "MUTUAL_FUND": AssetType.MUTUAL_FUND,
        "COLLECTIVE_INVESTMENT": AssetType.MUTUAL_FUND,
    }.get(normalized, AssetType.UNKNOWN)


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise ValueError("Option expiration is not a date")


def _canonical_symbol(value: object) -> str:
    return "".join(str(value or "").upper().split())
