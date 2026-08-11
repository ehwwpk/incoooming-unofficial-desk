from __future__ import annotations

import httpx
from sqlalchemy import inspect

from schwab_dashboard.application.errors import AuthenticationRequiredError
from schwab_dashboard.application.ports.dashboard import DashboardReader
from schwab_dashboard.application.services.read_dashboard import ReadDashboard
from schwab_dashboard.application.services.record_ledger_activity import RecordLedgerActivity
from schwab_dashboard.application.services.record_market_observations import (
    RecordMarketObservations,
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
from schwab_dashboard.infrastructure.database.uow import build_uow_factory
from schwab_dashboard.infrastructure.database.uow_market import build_market_uow_factory
from schwab_dashboard.infrastructure.database.uow_truth import build_truth_uow_factory
from schwab_dashboard.infrastructure.database.uow_workspace import build_workspace_uow_factory
from schwab_dashboard.infrastructure.demo.dashboard import DemoDashboardReader
from schwab_dashboard.infrastructure.schwab.gateway import (
    SchwabBrokerGateway,
    SchwabReadOnlyMarketDataClient,
    SchwabReadOnlyTraderClient,
)
from schwab_dashboard.infrastructure.schwab.mapper import SchwabAccountMapper
from schwab_dashboard.infrastructure.schwab.market_mapper import SchwabMarketMapper
from schwab_dashboard.infrastructure.schwab.oauth import SchwabOAuthClient
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
        self.oauth = self._build_oauth()

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
                "raw_broker_events",
                "raw_market_events",
                "sync_runs",
                "underlying_market_snapshots",
                "underlying_daily_bars",
                "workspace_preferences",
            }
            return required <= tables
        except Exception:
            return False

    def read_dashboard(self) -> DashboardReader:
        if self.settings.demo_mode:
            return DemoDashboardReader()
        return ReadDashboard(
            uow_factory=self.uow_factory,
            analytics_reader=SqlLiveAnalyticsReader(self.session_factory),
            credentials_configured=self.settings.schwab_credentials_configured,
            token_available=self.oauth.token_available() if self.oauth is not None else False,
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
        )

    def save_workspace_preferences(self) -> SaveWorkspacePreferences:
        return SaveWorkspacePreferences(uow_factory=self.workspace_uow_factory)

    def load_workspace_preferences(self) -> LoadWorkspacePreferences:
        return LoadWorkspacePreferences(uow_factory=self.workspace_uow_factory)

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
        self.engine.dispose()

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
