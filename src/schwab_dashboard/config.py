from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and an optional local `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    schwab_app_key: SecretStr | None = Field(default=None, alias="SCHWAB_APP_KEY")
    schwab_app_secret: SecretStr | None = Field(default=None, alias="SCHWAB_APP_SECRET")
    schwab_callback_url: str = Field(
        default="https://127.0.0.1:8182/",
        alias="SCHWAB_CALLBACK_URL",
    )

    data_dir: Path = Field(default=Path("var"), alias="SCHWAB_DASHBOARD_DATA_DIR")
    host: str = Field(default="127.0.0.1", alias="SCHWAB_DASHBOARD_HOST")
    port: int = Field(default=8182, alias="SCHWAB_DASHBOARD_PORT", ge=1, le=65535)
    log_level: str = Field(default="INFO", alias="SCHWAB_DASHBOARD_LOG_LEVEL")
    demo_mode: bool = Field(default=False, alias="SCHWAB_DASHBOARD_DEMO_MODE")
    campaign_chart_enabled: bool = Field(
        default=True,
        alias="SCHWAB_DASHBOARD_CAMPAIGN_CHART_ENABLED",
    )
    auto_sync_enabled: bool = Field(default=True, alias="SCHWAB_AUTO_SYNC_ENABLED")
    auto_sync_interval_seconds: int = Field(
        default=900,
        alias="SCHWAB_AUTO_SYNC_INTERVAL_SECONDS",
        ge=60,
        le=86400,
    )
    auto_sync_startup_delay_seconds: int = Field(
        default=2,
        alias="SCHWAB_AUTO_SYNC_STARTUP_DELAY_SECONDS",
        ge=0,
        le=300,
    )

    token_service_name: str = "schwab-options-dashboard"
    token_account_name: str = "personal-schwab-oauth"
    trader_base_url: str = "https://api.schwabapi.com/trader/v1"
    market_data_base_url: str = "https://api.schwabapi.com/marketdata/v1"
    oauth_authorize_url: str = "https://api.schwabapi.com/v1/oauth/authorize"
    oauth_token_url: str = "https://api.schwabapi.com/v1/oauth/token"
    parser_version: str = "schwab-accounts-v1"
    transaction_parser_version: str = "schwab-transactions-v1"
    market_parser_version: str = "schwab-market-v1"
    transaction_history_days: int = Field(default=365, ge=1, le=730)
    # These are personal defaults, not product capability limits. Radar may inspect
    # any non-negative DTE range returned by the configured market-data source.
    radar_minimum_dte: int = Field(default=5, ge=0)
    radar_maximum_dte: int = Field(default=60, ge=0)
    radar_minimum_annualized_rate_percent: Decimal = Field(default=Decimal("5"), ge=Decimal("0"))
    radar_maximum_spread_percent: Decimal = Field(default=Decimal("25"), ge=0)
    radar_minimum_open_interest: int = Field(default=0, ge=0)
    radar_minimum_volume: int = Field(default=0, ge=0)
    radar_maximum_quote_age_seconds: int = Field(default=86400, ge=30, le=86400)
    radar_maximum_five_day_move_percent: Decimal | None = Field(default=Decimal("20"), ge=0)
    radar_cache_seconds: int = Field(default=60, ge=0, le=3600)

    @property
    def resolved_data_dir(self) -> Path:
        return self.data_dir.expanduser().resolve()

    @property
    def database_url(self) -> str:
        database_path = (self.resolved_data_dir / "schwab-ledger.sqlite3").as_posix()
        return f"sqlite+pysqlite:///{database_path}"

    @property
    def schwab_credentials_configured(self) -> bool:
        return bool(
            self.schwab_app_key is not None
            and self.schwab_app_key.get_secret_value().strip()
            and self.schwab_app_secret is not None
            and self.schwab_app_secret.get_secret_value().strip()
        )

    def require_schwab_credentials(self) -> tuple[str, str]:
        if not self.schwab_credentials_configured:
            raise RuntimeError(
                "Schwab credentials are not configured. Set SCHWAB_APP_KEY and "
                "SCHWAB_APP_SECRET in the local .env file."
            )
        assert self.schwab_app_key is not None
        assert self.schwab_app_secret is not None
        return (
            self.schwab_app_key.get_secret_value(),
            self.schwab_app_secret.get_secret_value(),
        )
