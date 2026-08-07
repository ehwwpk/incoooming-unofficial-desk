from __future__ import annotations

import httpx
from sqlalchemy import inspect

from schwab_dashboard.application.errors import AuthenticationRequiredError
from schwab_dashboard.application.services.read_dashboard import ReadDashboard
from schwab_dashboard.application.services.sync_accounts import SyncAccountsAndPositions
from schwab_dashboard.config import Settings
from schwab_dashboard.infrastructure.database.engine import (
    create_database_engine,
    create_session_factory,
)
from schwab_dashboard.infrastructure.database.uow import build_uow_factory
from schwab_dashboard.infrastructure.schwab.gateway import (
    SchwabBrokerGateway,
    SchwabReadOnlyTraderClient,
)
from schwab_dashboard.infrastructure.schwab.mapper import SchwabAccountMapper
from schwab_dashboard.infrastructure.schwab.oauth import SchwabOAuthClient
from schwab_dashboard.infrastructure.secrets.keyring_tokens import KeyringTokenStore


class Container:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.engine = create_database_engine(self.settings.database_url)
        self.session_factory = create_session_factory(self.engine)
        self.uow_factory = build_uow_factory(self.session_factory)
        self.token_store = KeyringTokenStore(
            service_name=self.settings.token_service_name,
            account_name=self.settings.token_account_name,
        )
        self._oauth_http = httpx.Client(timeout=30.0, follow_redirects=False)
        self._trader_http = httpx.Client(timeout=30.0, follow_redirects=False)
        self.oauth = self._build_oauth()

    def database_ready(self) -> bool:
        try:
            tables = set(inspect(self.engine).get_table_names())
            return {"alembic_version", "sync_runs", "raw_broker_events", "accounts"} <= tables
        except Exception:
            return False

    def read_dashboard(self) -> ReadDashboard:
        return ReadDashboard(
            uow_factory=self.uow_factory,
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

    def require_oauth(self) -> SchwabOAuthClient:
        if self.oauth is None:
            raise AuthenticationRequiredError(
                "Schwab app credentials are missing from the local .env file."
            )
        return self.oauth

    def close(self) -> None:
        self._oauth_http.close()
        self._trader_http.close()
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
