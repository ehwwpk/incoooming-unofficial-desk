from __future__ import annotations

import json
import sys
import webbrowser
from pathlib import Path
from typing import NoReturn

import typer
import uvicorn
from alembic import command
from alembic.config import Config

from schwab_dashboard.app import create_app
from schwab_dashboard.application.campaigns import reconcile_option_campaigns
from schwab_dashboard.application.campaigns.audit import audit_campaign_ledger
from schwab_dashboard.application.errors import (
    AuthenticationRequiredError,
    BrokerRequestError,
    CredentialStoreError,
)
from schwab_dashboard.config import Settings
from schwab_dashboard.container import Container
from schwab_dashboard.infrastructure.database.analytics_reader import SqlLiveAnalyticsReader
from schwab_dashboard.infrastructure.runtime.identity import current_build_id
from schwab_dashboard.infrastructure.runtime.launcher import LocalServerError, local_listener
from schwab_dashboard.infrastructure.runtime.platform_commands import dashboard_command

app = typer.Typer(no_args_is_help=True, help="Incoooming local commands.")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(__file__).resolve().parent


def _alembic_config(settings: Settings) -> Config:
    source_migrations = PROJECT_ROOT / "migrations"
    runtime_root = PROJECT_ROOT if source_migrations.is_dir() else PACKAGE_ROOT
    config = Config(str(runtime_root / "alembic.ini"))
    config.set_main_option("script_location", str(runtime_root / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    return config


def _upgrade_database(settings: Settings, *, announce: bool) -> None:
    settings.resolved_data_dir.mkdir(parents=True, exist_ok=True)
    command.upgrade(_alembic_config(settings), "head")
    if announce:
        typer.echo(f"Database is current: {settings.resolved_data_dir}")


def _not_ready(exc: AuthenticationRequiredError | BrokerRequestError) -> NoReturn:
    typer.echo(f"Not ready: {exc}", err=True)
    raise typer.Exit(code=1)


@app.command("db-upgrade")
def db_upgrade() -> None:
    """Apply all database migrations."""
    settings = Settings()
    _upgrade_database(settings, announce=True)


@app.command("auth-url")
def auth_url() -> None:
    """Print the Schwab authorization URL to open in a browser."""
    container = Container()
    try:
        try:
            typer.echo(container.require_oauth().authorization_url())
        except (AuthenticationRequiredError, BrokerRequestError) as exc:
            _not_ready(exc)
    finally:
        container.close()


@app.command("auth-complete")
def auth_complete(
    callback_url: str | None = typer.Argument(
        default=None,
        help="Entire URL from the browser address bar after Schwab authorization.",
    ),
    from_stdin: bool = typer.Option(
        default=False,
        help="Read the callback URL from standard input without echoing it.",
    ),
) -> None:
    """Finish Schwab login and save the connection in your system credential store."""
    if from_stdin:
        pasted_url = sys.stdin.readline().strip()
        if not pasted_url:
            typer.echo("Not ready: no callback URL was received on standard input.", err=True)
            raise typer.Exit(code=1)
    else:
        pasted_url = callback_url or typer.prompt("Paste the entire callback URL", hide_input=True)
    container = Container()
    try:
        try:
            token = container.require_oauth().exchange_callback_url(pasted_url)
            typer.echo(
                f"Authorization stored. Access token expires at {token.expires_at.isoformat()}."
            )
        except (AuthenticationRequiredError, BrokerRequestError) as exc:
            _not_ready(exc)
    finally:
        container.close()


@app.command("auth-connect")
def auth_connect(
    no_browser: bool = typer.Option(False, help="Print the login link instead of opening it."),
    no_sync: bool = typer.Option(False, help="Save the connection without the first account sync."),
) -> None:
    """Guide you through Schwab login, save the connection, and sync your account."""
    container = Container()
    try:
        try:
            oauth = container.require_oauth()
            # Container already checked storage. Reuse its safe diagnostic so
            # denied Keychain access does not immediately prompt a second time.
            if container.credential_store_error:
                raise CredentialStoreError(container.credential_store_error)
            _upgrade_database(container.settings, announce=False)
            authorization_url = oauth.authorization_url()
            typer.echo("Approve Incoooming in Schwab's browser login.")
            opened = False
            if not no_browser:
                try:
                    opened = webbrowser.open(authorization_url)
                except (webbrowser.Error, OSError):
                    pass
            if not opened:
                typer.echo("Open this link in your browser:")
                typer.echo(authorization_url)
            typer.echo(
                "When Schwab returns you to the local callback address, the page may not load. "
                "Copy its entire address and paste it below. The paste stays hidden; "
                "do not share the address or paste it into a chat."
            )
            pasted_url = typer.prompt("Paste the entire callback URL", hide_input=True)
            oauth.exchange_callback_url(pasted_url)
            typer.echo("Schwab authorization is saved in your system credential store.")
            if not no_sync:
                try:
                    full = container.sync_full(trigger="cli")
                except (AuthenticationRequiredError, BrokerRequestError):
                    typer.echo(
                        "Login finished, but the first sync could not complete. "
                        "After fixing the issue below, run "
                        f"`{dashboard_command('sync')}` from the project folder again.",
                        err=True,
                    )
                    raise
                typer.echo(
                    f"First sync complete: {full.accounts.account_count} account(s), "
                    f"{full.accounts.position_count} position(s)."
                )
        except (AuthenticationRequiredError, BrokerRequestError) as exc:
            _not_ready(exc)
    finally:
        container.close()


@app.command("auth-clear")
def auth_clear() -> None:
    """Remove the stored Schwab token without changing app credentials."""
    container = Container()
    try:
        try:
            # Logging out is a local action and still works after app keys have
            # been removed from .env or the saved token has become unreadable.
            container.require_live_mode()
            container.token_store.delete()
            typer.echo("Stored Schwab OAuth token removed.")
        except (AuthenticationRequiredError, BrokerRequestError) as exc:
            _not_ready(exc)
    finally:
        container.close()


@app.command()
def sync() -> None:
    """Refresh Schwab positions, one year of activity, quotes, Greeks, and price history."""
    container = Container()
    try:
        try:
            full = container.sync_full(trigger="cli")
            result = full.accounts
            activity = full.activity
            market = full.market
            typer.echo(
                f"Sync {result.run_id} completed: {result.account_count} account(s), "
                f"{result.position_count} position(s), "
                f"{activity.transaction_count} transaction(s), "
                f"{market.option_quote_count} option quote(s), "
                f"{market.daily_bar_count} daily price bar(s), "
                f"{market.intraday_bar_count} intraday price bar(s), "
                f"{result.warning_count} warning(s)."
            )
        except (AuthenticationRequiredError, BrokerRequestError) as exc:
            _not_ready(exc)
    finally:
        container.close()


@app.command()
def doctor() -> None:
    """Report local configuration and connection readiness without printing secrets."""
    container = Container()
    try:
        typer.echo(f"Database ready: {container.database_ready()}")
        typer.echo(
            f"Schwab credentials configured: {container.settings.schwab_credentials_configured}"
        )
        typer.echo(f"Schwab token available: {container.token_available()}")
        typer.echo(f"Callback URL: {container.settings.schwab_callback_url}")
        typer.echo(f"Loopback server: {container.settings.host}:{container.settings.port}")
        typer.echo(f"Expected local build: {current_build_id()}")
        if container.credential_store_error:
            _not_ready(CredentialStoreError(container.credential_store_error))
    finally:
        container.close()


@app.command("runtime-id", hidden=True)
def runtime_id() -> None:
    """Print the current application fingerprint for the local launcher."""

    typer.echo(current_build_id())


@app.command("runtime-config", hidden=True)
def runtime_config() -> None:
    """Print the non-secret local address and build identity for the launcher."""

    settings = Settings()
    typer.echo(
        json.dumps(
            {
                "host": settings.host,
                "port": settings.port,
                "build_id": current_build_id(),
            }
        )
    )


@app.command("campaign-audit")
def campaign_audit() -> None:
    """Audit local short-premium campaign links without printing account details."""

    container = Container()
    try:
        reader = SqlLiveAnalyticsReader(container.session_factory)
        executions = reader.list_executions()
        lifecycle = reader.list_lifecycle_events()
        audit = audit_campaign_ledger(
            reconcile_option_campaigns(executions, lifecycle),
            executions,
            lifecycle,
        )
        typer.echo(f"Campaigns: {audit.campaigns}")
        typer.echo(
            "Confidence: "
            f"{audit.exact_campaigns} exact / {audit.inferred_campaigns} inferred / "
            f"{audit.unknown_campaigns} unknown"
        )
        typer.echo(f"Excluded long-option lifecycle events: {audit.excluded_long_lifecycle_events}")
        typer.echo(f"Nonstandard-contract events observed: {audit.nonstandard_contract_events}")
        typer.echo(
            "Campaign cash: "
            f"{audit.campaign_net_cash} / source cash {audit.source_net_cash} / "
            f"variance {audit.cash_variance}"
        )
        typer.echo(
            f"Legacy chart removal gate: {'PASS' if audit.legacy_removal_gate_passed else 'HOLD'}"
        )
    finally:
        container.close()


@app.command()
def serve() -> None:
    """Run Incoooming locally."""
    settings = Settings()
    try:
        with local_listener(settings.host, settings.port) as listener:
            _upgrade_database(settings, announce=False)
            config = uvicorn.Config(
                create_app(),
                host=settings.host,
                port=settings.port,
                log_level=settings.log_level.lower(),
            )
            typer.echo(
                f"Open http://{settings.host}:{settings.port}/ in your browser. "
                "Keep this window open; Ctrl+C stops Incoooming."
            )
            uvicorn.Server(config).run(sockets=[listener])
    except LocalServerError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def demo() -> None:
    """Run Incoooming with fictional data; the real ledger is never modified."""
    settings = Settings(demo_mode=True)
    try:
        with local_listener(settings.host, settings.port) as listener:
            _upgrade_database(settings, announce=False)
            container = Container(settings)
            try:
                config = uvicorn.Config(
                    create_app(container),
                    host=settings.host,
                    port=settings.port,
                    log_level=settings.log_level.lower(),
                )
                typer.echo(
                    f"Open http://{settings.host}:{settings.port}/ in your browser. "
                    "Keep this window open; Ctrl+C stops the demo."
                )
                uvicorn.Server(config).run(sockets=[listener])
            finally:
                container.close()
    except LocalServerError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
