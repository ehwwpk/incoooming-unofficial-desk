from __future__ import annotations

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
