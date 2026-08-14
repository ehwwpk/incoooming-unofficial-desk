from __future__ import annotations

from datetime import timedelta

import httpx
from sqlalchemy import inspect

from schwab_dashboard.application.errors import AuthenticationRequiredError
from schwab_dashboard.application.ports.dashboard import DashboardReader
from schwab_dashboard.application.ports.opportunity_market import OpportunityMarketGateway
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
        self._runtime_cache = GenerationCache()
        self._analytics_reader = SqlLiveAnalyticsReader(self.session_factory)
        self._live_dashboard_reader = CachedDashboardReader(
            delegate=ReadDashboard(
                uow_factory=self.uow_factory,
                analytics_reader=self._analytics_reader,
                credentials_configured=self.settings.schwab_credentials_configured,
                token_available=(self.oauth.token_available() if self.oauth is not None else False),
            ),
            cache=self._runtime_cache,
            key=("dashboard", "schwab"),
        )
        self._live_campaign_chart_reader = CachedCampaignChartReader(
            delegate=ReadLiveCampaignChart(
                uow_factory=self.uow_factory,
                analytics_reader=self._analytics_reader,
            ),
            cache=self._runtime_cache,
            key_prefix=("campaign-chart", "schwab"),
        )
        self.opportunity_store = SqlOpportunityStore(self.session_factory)
        self.source_store = SqlSourceDatasetStore(self.session_factory)
        self.market_history_refresh = MarketHistoryRefreshPolicy(
            minimum_interval=timedelta(hours=1)
        )
        self._radar_service = self._build_radar_service()
        self.sync_coordinator = FullSyncCoordinator(
            accounts_factory=self.sync_accounts,
            activity_factory=self.sync_transactions,
            market_factory=self.sync_market_data,
            enabled=self.settings.auto_sync_enabled and not self.settings.demo_mode,
            interval_seconds=self.settings.auto_sync_interval_seconds,
            uow_factory=self.uow_factory,
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
        )

    def sync_full(self, *, trigger: str) -> FullSyncResult:
        result = self.sync_coordinator.execute(trigger=trigger)
        self._runtime_cache.invalidate()
        return result

    def token_available(self) -> bool:
        return self.oauth.token_available() if self.oauth is not None else False

    def save_workspace_preferences(self) -> SaveWorkspacePreferences:
        return SaveWorkspacePreferences(uow_factory=self.workspace_uow_factory)

    def load_workspace_preferences(self) -> LoadWorkspacePreferences:
        return LoadWorkspacePreferences(uow_factory=self.workspace_uow_factory)

    def premium_radar(self) -> RunPremiumRadar:
        return self._radar_service

    def import_csv_dataset(self) -> ImportCsvDataset:
        return ImportCsvDataset(store=self.source_store)

    def require_oauth(self) -> SchwabOAuthClient:
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

    def _build_radar_service(self) -> RunPremiumRadar:
        market: OpportunityMarketGateway
        if self.settings.demo_mode:
            market = DemoOpportunityMarketGateway()
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
            store=self.opportunity_store,
            dashboard_factory=self.read_dashboard,
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
        )

    def _build_oauth(self) -> SchwabOAuthClient | None:
        if not self.settings.schwab_credentials_configured:
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
