from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import inspect

from schwab_dashboard.application.errors import AuthenticationRequiredError, CredentialStoreError
from schwab_dashboard.application.market_time import option_session_cache_partition
from schwab_dashboard.application.performance.models import PerformanceComparison
from schwab_dashboard.application.performance.periods import PerformancePeriod
from schwab_dashboard.application.performance.projection import METHODOLOGY_VERSION
from schwab_dashboard.application.ports.dashboard import DashboardReader
from schwab_dashboard.application.ports.opportunity_market import OpportunityMarketGateway
from schwab_dashboard.application.ports.opportunity_store import OpportunityStore
from schwab_dashboard.application.services.cached_campaign_chart import (
    CachedCampaignChartReader,
)
from schwab_dashboard.application.services.full_sync import (
    FullSyncCoordinator,
    FullSyncResult,
)
from schwab_dashboard.application.services.import_csv_dataset import ImportCsvDataset
from schwab_dashboard.application.services.market_history_refresh import (
    MarketHistoryRefreshPolicy,
)
from schwab_dashboard.application.services.read_campaign_chart import (
    ReadLiveCampaignChart,
    ReadSnapshotCampaignChart,
)
from schwab_dashboard.application.services.read_dashboard import ReadDashboard
from schwab_dashboard.application.services.read_performance_comparison import (
    ReadPerformanceComparison,
)
from schwab_dashboard.application.services.record_ledger_activity import RecordLedgerActivity
from schwab_dashboard.application.services.record_market_observations import (
    RecordMarketObservations,
)
from schwab_dashboard.application.services.run_premium_radar import (
    AuthorizationRequiredOpportunityMarketGateway,
    RadarDefaults,
    RunPremiumRadar,
)
from schwab_dashboard.application.services.runtime_cache import (
    CachedDashboardReader,
    GenerationCache,
)
from schwab_dashboard.application.services.sync_accounts import SyncAccountsAndPositions
from schwab_dashboard.application.services.sync_market import SyncSchwabMarketData
from schwab_dashboard.application.services.sync_transactions import SyncSchwabTransactions
from schwab_dashboard.application.services.workspace_preferences import (
    LoadWorkspacePreferences,
    SaveWorkspacePreferences,
)
from schwab_dashboard.config import Settings
from schwab_dashboard.infrastructure.database.analytics_reader import SqlLiveAnalyticsReader
from schwab_dashboard.infrastructure.database.engine import (
    create_database_engine,
    create_session_factory,
)
from schwab_dashboard.infrastructure.database.opportunity_store import SqlOpportunityStore
from schwab_dashboard.infrastructure.database.source_store import SqlSourceDatasetStore
from schwab_dashboard.infrastructure.database.uow import build_uow_factory
from schwab_dashboard.infrastructure.database.uow_market import build_market_uow_factory
from schwab_dashboard.infrastructure.database.uow_truth import build_truth_uow_factory
from schwab_dashboard.infrastructure.database.uow_workspace import build_workspace_uow_factory
from schwab_dashboard.infrastructure.demo.dashboard import DemoDashboardReader
from schwab_dashboard.infrastructure.demo.opportunity import DemoOpportunityMarketGateway
from schwab_dashboard.infrastructure.demo.opportunity_store import DemoOpportunityStore
from schwab_dashboard.infrastructure.imports import CsvDashboardReader
from schwab_dashboard.infrastructure.schwab.gateway import (
    SchwabBrokerGateway,
    SchwabReadOnlyMarketDataClient,
    SchwabReadOnlyTraderClient,
)
from schwab_dashboard.infrastructure.schwab.mapper import SchwabAccountMapper
from schwab_dashboard.infrastructure.schwab.market_mapper import SchwabMarketMapper
from schwab_dashboard.infrastructure.schwab.oauth import SchwabOAuthClient
from schwab_dashboard.infrastructure.schwab.opportunity_gateway import (
    SchwabOpportunityMarketGateway,
)
from schwab_dashboard.infrastructure.schwab.transaction_mapper import SchwabTransactionMapper
from schwab_dashboard.infrastructure.secrets.keyring_tokens import KeyringTokenStore


class Container:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.engine = create_database_engine(self.settings.database_url)
        self.session_factory = create_session_factory(self.engine)
        self.uow_factory = build_uow_factory(self.session_factory)
        self.truth_uow_factory = build_truth_uow_factory(self.session_factory)
        self.market_uow_factory = build_market_uow_factory(self.session_factory)
        self.workspace_uow_factory = build_workspace_uow_factory(self.session_factory)
        self.token_store = KeyringTokenStore(
            service_name=self.settings.token_service_name,
            account_name=self.settings.token_account_name,
        )
        self._oauth_http = httpx.Client(timeout=30.0, follow_redirects=False)
        self._trader_http = httpx.Client(timeout=30.0, follow_redirects=False)
        self._market_http = httpx.Client(timeout=30.0, follow_redirects=False)
        self._radar_http = httpx.Client(timeout=30.0, follow_redirects=False)
        self.oauth = self._build_oauth()
        self.credential_store_error: str | None = None
        self._last_token_available = False
        self._runtime_cache = GenerationCache()
        self.token_available()
        self._analytics_reader = SqlLiveAnalyticsReader(self.session_factory)
        self._live_dashboard_reader = CachedDashboardReader(
            delegate=ReadDashboard(
                uow_factory=self.uow_factory,
                analytics_reader=self._analytics_reader,
                credentials_configured=self.settings.schwab_credentials_configured,
                token_available=lambda: self._last_token_available,
                margin_interest_rate_percent=self.settings.margin_interest_rate_percent,
            ),
            cache=self._runtime_cache,
            key=("dashboard", "schwab"),
            cache_partition=_live_option_session_partition,
        )
        self._live_campaign_chart_reader = CachedCampaignChartReader(
            delegate=ReadLiveCampaignChart(
                uow_factory=self.uow_factory,
                analytics_reader=self._analytics_reader,
            ),
            cache=self._runtime_cache,
            key_prefix=("campaign-chart", "schwab"),
            cache_partition=_live_option_session_partition,
        )
        self._performance_comparison_reader = ReadPerformanceComparison(
            analytics_reader=self._analytics_reader,
            margin_interest_rate_percent=self.settings.margin_interest_rate_percent,
        )
        self.opportunity_store = SqlOpportunityStore(self.session_factory)
        self.source_store = SqlSourceDatasetStore(self.session_factory)
        self.market_history_refresh = MarketHistoryRefreshPolicy(
            minimum_interval=timedelta(hours=1)
        )
        self._radar_service = self._build_radar_service(demo=self.settings.demo_mode)
        self._demo_radar_service = (
            self._radar_service if self.settings.demo_mode else self._build_radar_service(demo=True)
        )
        self.sync_coordinator = FullSyncCoordinator(
            accounts_factory=self.sync_accounts,
            activity_factory=self.sync_transactions,
            market_factory=self.sync_market_data,
            enabled=self.settings.auto_sync_enabled and not self.settings.demo_mode,
            interval_seconds=self.settings.auto_sync_interval_seconds,
            uow_factory=self.uow_factory,
            on_success=self._runtime_cache.invalidate,
        )

    def database_ready(self) -> bool:
        try:
            tables = set(inspect(self.engine).get_table_names())
            required = {
                "accounts",
                "account_balance_snapshots",
                "alembic_version",
                "cash_movements",
                "executions",
                "instruments",
                "option_lifecycle_events",
                "option_market_snapshots",
                "radar_candidate_snapshots",
                "radar_lookup_runs",
                "radar_policies",
                "radar_saved_symbols",
                "raw_broker_events",
                "raw_market_events",
                "source_datasets",
                "source_import_files",
                "source_import_records",
                "sync_runs",
                "underlying_market_snapshots",
                "underlying_daily_bars",
                "underlying_intraday_bars",
                "workspace_preferences",
            }
            return required <= tables
        except Exception:
            return False

    def read_dashboard(self, source_key: str | None = None) -> DashboardReader:
        normalized_source = source_key or "schwab"
        if self.settings.demo_mode or normalized_source == "demo":
            return CachedDashboardReader(
                delegate=DemoDashboardReader(),
                cache=self._runtime_cache,
                key=("dashboard", "demo"),
            )
        if normalized_source.startswith("csv:"):
            return CachedDashboardReader(
                delegate=CsvDashboardReader(
                    store=self.source_store,
                    dataset_id=normalized_source.removeprefix("csv:"),
                ),
                cache=self._runtime_cache,
                key=("dashboard", normalized_source),
            )
        return self._live_dashboard_reader

    def read_campaign_chart(self, source_key: str | None = None) -> CachedCampaignChartReader:
        normalized_source = source_key or "schwab"
        if normalized_source == "schwab" and not self.settings.demo_mode:
            return self._live_campaign_chart_reader
        return CachedCampaignChartReader(
            delegate=ReadSnapshotCampaignChart(self.read_dashboard(normalized_source)),
            cache=self._runtime_cache,
            key_prefix=("campaign-chart", normalized_source),
        )

    def read_performance_comparison(self, period: PerformancePeriod) -> PerformanceComparison:
        return self._runtime_cache.get_or_load(
            (
                (
                    "performance-comparison",
                    METHODOLOGY_VERSION,
                    "schwab",
                    period.value,
                ),
                _live_option_session_partition(),
            ),
            lambda: self._performance_comparison_reader.execute(period),
        )

    def sync_accounts(self) -> SyncAccountsAndPositions:
        oauth = self.require_oauth()
        trader_client = SchwabReadOnlyTraderClient(
            base_url=self.settings.trader_base_url,
            oauth=oauth,
            http_client=self._trader_http,
        )
        gateway = SchwabBrokerGateway(client=trader_client, mapper=SchwabAccountMapper())
        return SyncAccountsAndPositions(
            broker=gateway,
            uow_factory=self.uow_factory,
            parser_version=self.settings.parser_version,
        )

    def record_ledger_activity(self) -> RecordLedgerActivity:
        return RecordLedgerActivity(uow_factory=self.truth_uow_factory)

    def record_market_observations(self) -> RecordMarketObservations:
        return RecordMarketObservations(uow_factory=self.market_uow_factory)

    def sync_transactions(self) -> SyncSchwabTransactions:
        oauth = self.require_oauth()
        client = SchwabReadOnlyTraderClient(
            base_url=self.settings.trader_base_url,
            oauth=oauth,
            http_client=self._trader_http,
        )
        return SyncSchwabTransactions(
            client=client,
            mapper=SchwabTransactionMapper(),
            ledger=self.record_ledger_activity(),
            uow_factory=self.uow_factory,
            parser_version=self.settings.transaction_parser_version,
            history_days=self.settings.transaction_history_days,
        )

    def sync_market_data(self) -> SyncSchwabMarketData:
        oauth = self.require_oauth()
        client = SchwabReadOnlyMarketDataClient(
            base_url=self.settings.market_data_base_url,
            oauth=oauth,
            http_client=self._market_http,
        )
        return SyncSchwabMarketData(
            client=client,
            mapper=SchwabMarketMapper(),
            recorder=self.record_market_observations(),
            uow_factory=self.uow_factory,
            parser_version=self.settings.market_parser_version,
            history_refresh_policy=self.market_history_refresh,
            analytics_reader=self._analytics_reader,
        )

    def sync_full(self, *, trigger: str) -> FullSyncResult:
        # Validate configuration before the coordinator records a sync run.
        # A fresh checkout may not have a migrated database yet, and missing
        # credentials should still produce the actionable authorization error.
        self.require_oauth()
        result = self.sync_coordinator.execute(trigger=trigger)
        self._runtime_cache.invalidate()
        return result

    def token_available(self) -> bool:
        self.credential_store_error = None
        try:
            available = self.oauth.token_available() if self.oauth is not None else False
        except CredentialStoreError as exc:
            self.credential_store_error = str(exc)
            available = False
        if available != self._last_token_available:
            self._last_token_available = available
            # Financial reads stay cached, but connection labels must follow an
            # unlock, reconnect, or logout observed by the readiness probe.
            self._runtime_cache.invalidate()
        return available

    def save_workspace_preferences(self) -> SaveWorkspacePreferences:
        return SaveWorkspacePreferences(uow_factory=self.workspace_uow_factory)

    def load_workspace_preferences(self) -> LoadWorkspacePreferences:
        return LoadWorkspacePreferences(uow_factory=self.workspace_uow_factory)

    def premium_radar(self, source_key: str | None = None) -> RunPremiumRadar:
        if self.settings.demo_mode or source_key == "demo":
            return self._demo_radar_service
        return self._radar_service

    def import_csv_dataset(self) -> ImportCsvDataset:
        return ImportCsvDataset(store=self.source_store)

    def require_live_mode(self) -> None:
        if self.settings.demo_mode:
            raise AuthenticationRequiredError(
                "Schwab is disabled because SCHWAB_DASHBOARD_DEMO_MODE is true. "
                "Set it to false in your environment or local .env file, then retry. "
                "Use the demo launcher when you want the fictional book."
            )

    def require_oauth(self) -> SchwabOAuthClient:
        self.require_live_mode()
        if self.oauth is None:
            raise AuthenticationRequiredError(
                "Schwab app credentials are missing from the local .env file."
            )
        return self.oauth

    def close(self) -> None:
        self._oauth_http.close()
        self._trader_http.close()
        self._market_http.close()
        self._radar_http.close()
        self.engine.dispose()

    def _build_radar_service(self, *, demo: bool) -> RunPremiumRadar:
        market: OpportunityMarketGateway
        store: OpportunityStore = self.opportunity_store
        clock: Callable[[], datetime] | None = None
        if demo:
            demo_as_of = self.read_dashboard("demo").execute().as_of

            def demo_clock() -> datetime:
                return demo_as_of

            clock = demo_clock
            market = DemoOpportunityMarketGateway(clock=clock)
            store = DemoOpportunityStore()
            source = "demo"
        elif self.oauth is None:
            market = AuthorizationRequiredOpportunityMarketGateway()
            source = "schwab"
        else:
            market = SchwabOpportunityMarketGateway(
                client=SchwabReadOnlyMarketDataClient(
                    base_url=self.settings.market_data_base_url,
                    oauth=self.oauth,
                    http_client=self._radar_http,
                ),
                mapper=SchwabMarketMapper(),
                recorder=self.record_market_observations(),
                parser_version=f"{self.settings.market_parser_version}-radar",
                cache_seconds=self.settings.radar_cache_seconds,
            )
            source = "schwab"
        return RunPremiumRadar(
            market=market,
            store=store,
            dashboard_factory=lambda: self.read_dashboard(source),
            defaults=RadarDefaults(
                minimum_dte=self.settings.radar_minimum_dte,
                maximum_dte=self.settings.radar_maximum_dte,
                minimum_annualized_rate_percent=(
                    self.settings.radar_minimum_annualized_rate_percent
                ),
                maximum_spread_percent=self.settings.radar_maximum_spread_percent,
                minimum_open_interest=self.settings.radar_minimum_open_interest,
                minimum_volume=self.settings.radar_minimum_volume,
                maximum_quote_age_seconds=self.settings.radar_maximum_quote_age_seconds,
                maximum_five_day_move_percent=(self.settings.radar_maximum_five_day_move_percent),
            ),
            source=source,
            clock=clock,
        )

    def _build_oauth(self) -> SchwabOAuthClient | None:
        if self.settings.demo_mode or not self.settings.schwab_credentials_configured:
            return None
        app_key, app_secret = self.settings.require_schwab_credentials()
        return SchwabOAuthClient(
            app_key=app_key,
            app_secret=app_secret,
            callback_url=self.settings.schwab_callback_url,
            authorize_url=self.settings.oauth_authorize_url,
            token_url=self.settings.oauth_token_url,
            token_store=self.token_store,
            http_client=self._oauth_http,
        )


def _live_option_session_partition() -> tuple[object, ...]:
    """Keep cached live views from crossing an expiration-session boundary."""

    return option_session_cache_partition(datetime.now(UTC))
