from __future__ import annotations

from pathlib import Path

import typer
import uvicorn
from alembic import command
from alembic.config import Config

from schwab_dashboard.app import create_app
from schwab_dashboard.config import Settings
from schwab_dashboard.container import Container

app = typer.Typer(no_args_is_help=True, help="Local Schwab options dashboard commands.")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config(settings: Settings) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    return config


@app.command("db-upgrade")
def db_upgrade() -> None:
    """Apply all database migrations."""
    settings = Settings()
    settings.resolved_data_dir.mkdir(parents=True, exist_ok=True)
    command.upgrade(_alembic_config(settings), "head")
    typer.echo(f"Database is current: {settings.resolved_data_dir}")


@app.command("auth-url")
def auth_url() -> None:
    """Print the Schwab authorization URL to open in a browser."""
    container = Container()
    try:
        typer.echo(container.require_oauth().authorization_url())
    finally:
        container.close()


@app.command("auth-complete")
def auth_complete(
    callback_url: str | None = typer.Argument(
        default=None,
        help="Entire URL from the browser address bar after Schwab authorization.",
    ),
) -> None:
    """Exchange a pasted Schwab callback URL and store the token in Windows Credential Manager."""
    pasted_url = callback_url or typer.prompt("Paste the entire callback URL", hide_input=True)
    container = Container()
    try:
        token = container.require_oauth().exchange_callback_url(pasted_url)
        typer.echo(f"Authorization stored. Access token expires at {token.expires_at.isoformat()}.")
    finally:
        container.close()


@app.command("auth-clear")
def auth_clear() -> None:
    """Remove the stored Schwab token without changing app credentials."""
    container = Container()
    try:
        container.require_oauth().clear_token()
        typer.echo("Stored Schwab OAuth token removed.")
    finally:
        container.close()


@app.command()
def sync() -> None:
    """Read current Schwab accounts and positions into the local ledger."""
    container = Container()
    try:
        result = container.sync_accounts().execute()
        typer.echo(
            f"Sync {result.run_id} completed: {result.account_count} account(s), "
            f"{result.position_count} position(s), {result.warning_count} warning(s)."
        )
    finally:
        container.close()


@app.command()
def doctor() -> None:
    """Report local configuration and connection readiness without printing secrets."""
    container = Container()
    try:
        oauth = container.oauth
        typer.echo(f"Database ready: {container.database_ready()}")
        typer.echo(
            f"Schwab credentials configured: {container.settings.schwab_credentials_configured}"
        )
        typer.echo(f"Schwab token available: {oauth.token_available() if oauth else False}")
        typer.echo(f"Callback URL: {container.settings.schwab_callback_url}")
        typer.echo(f"Loopback server: {container.settings.host}:{container.settings.port}")
    finally:
        container.close()


@app.command()
def serve() -> None:
    """Run the private local dashboard."""
    settings = Settings()
    uvicorn.run(
        create_app(),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    app()
