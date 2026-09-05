from __future__ import annotations

import webbrowser
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from schwab_dashboard import cli
from schwab_dashboard.application.errors import BrokerRequestError, CredentialStoreError
from schwab_dashboard.application.ports.tokens import OAuthTokenSet
from schwab_dashboard.config import Settings
from schwab_dashboard.infrastructure.schwab.oauth import SchwabOAuthClient
from tests.fakes import MemoryTokenStore

CALLBACK = "https://127.0.0.1:8182/?code=dummy-private-code"


class FailingStore(MemoryTokenStore):
    read_error: CredentialStoreError | None = None
    save_error: CredentialStoreError | None = None

    def load(self) -> OAuthTokenSet | None:
        if self.read_error:
            raise self.read_error
        return super().load()

    def save(self, token: OAuthTokenSet) -> None:
        if self.save_error:
            raise self.save_error
        super().save(token)


class ConnectContainer:
    def __init__(self, tmp_path: Path) -> None:
        self.settings = Settings(_env_file=None, data_dir=tmp_path)
        self.token_store = FailingStore()
        self.closed = False
        self.synced = False
        self.requests: list[httpx.Request] = []
        self.sync_error: BrokerRequestError | None = None
        self.http = httpx.Client(transport=httpx.MockTransport(self.respond))
        self.oauth = SchwabOAuthClient(
            app_key="dummy-key",
            app_secret="dummy-secret",
            callback_url="https://127.0.0.1:8182/",
            authorize_url="https://broker.example/authorize",
            token_url="https://broker.example/token",
            token_store=self.token_store,
            http_client=self.http,
        )

    @property
    def credential_store_error(self) -> str | None:
        error = self.token_store.read_error
        return str(error) if error else None

    def respond(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(
            200,
            json={"access_token": "dummy-access", "refresh_token": "dummy-refresh"},
        )

    def require_oauth(self) -> SchwabOAuthClient:
        return self.oauth

    def sync_full(self, *, trigger: str) -> Any:
        assert self.token_store.token is not None
        assert trigger == "cli"
        if self.sync_error:
            raise self.sync_error
        self.synced = True
        return SimpleNamespace(accounts=SimpleNamespace(account_count=1, position_count=3))

    def close(self) -> None:
        self.closed = True
        self.http.close()


@pytest.fixture()
def container(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ConnectContainer:
    fake = ConnectContainer(tmp_path)
    monkeypatch.setattr(cli, "Container", lambda: fake)
    monkeypatch.setattr(cli, "_upgrade_database", lambda *args, **kwargs: None)
    return fake


def test_guided_login_uses_hidden_callback_and_syncs_after_saving(
    container: ConnectContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(url) or True)
    result = CliRunner().invoke(cli.app, ["auth-connect"], input=CALLBACK + "\n")
    assert result.exit_code == 0, result.output
    assert opened and opened[0].startswith("https://broker.example/authorize?")
    assert "First sync complete: 1 account(s), 3 position(s)." in result.output
    assert "dummy-private-code" not in result.output
    assert "dummy-secret" not in result.output
    assert "dummy-access" not in result.output
    assert "dummy-refresh" not in result.output
    assert container.synced and container.closed
    assert len(container.requests) == 1
    assert container.requests[0].url.path == "/token"


def test_manual_login_flags_skip_browser_and_account_sync(
    container: ConnectContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_open(url: str) -> bool:
        raise AssertionError("No browser should be opened")

    monkeypatch.setattr(cli.webbrowser, "open", unexpected_open)
    result = CliRunner().invoke(
        cli.app, ["auth-connect", "--no-browser", "--no-sync"], input=CALLBACK + "\n"
    )
    assert result.exit_code == 0
    assert "Open this link in your browser:" in result.output
    assert "https://broker.example/authorize?" in result.output
    assert container.token_store.token is not None
    assert not container.synced
    assert container.closed


@pytest.mark.parametrize("failure", [False, webbrowser.Error("dummy-browser-detail")])
def test_unavailable_browser_falls_back_to_link(
    container: ConnectContainer, monkeypatch: pytest.MonkeyPatch, failure: object
) -> None:
    def unavailable(url: str) -> bool:
        if isinstance(failure, Exception):
            raise failure
        return False

    monkeypatch.setattr(cli.webbrowser, "open", unavailable)
    result = CliRunner().invoke(cli.app, ["auth-connect", "--no-sync"], input=CALLBACK + "\n")
    assert result.exit_code == 0
    assert "Open this link" in result.output
    assert "dummy-browser-detail" not in result.output


def test_cancelled_callback_does_not_exchange_or_sync(container: ConnectContainer) -> None:
    result = CliRunner().invoke(cli.app, ["auth-connect", "--no-browser"], input="")
    assert result.exit_code == 1
    assert "Aborted" in result.output
    assert not container.requests
    assert not container.synced
    assert container.token_store.token is None
    assert container.closed


def test_wrong_callback_does_not_exchange_or_sync(container: ConnectContainer) -> None:
    result = CliRunner().invoke(
        cli.app,
        ["auth-connect", "--no-browser"],
        input="https://wrong.example/?code=dummy-private-code\n",
    )
    assert result.exit_code == 1
    assert "does not match" in result.output
    assert "dummy-private-code" not in result.output
    assert not container.requests
    assert not container.synced
    assert container.closed


def test_locked_storage_is_reported_before_requesting_browser_login(
    container: ConnectContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    container.token_store.read_error = CredentialStoreError("Unlock macOS Keychain and retry.")
    opened: list[str] = []
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(url) or True)
    result = CliRunner().invoke(cli.app, ["auth-connect"])
    assert result.exit_code == 1
    assert "Not ready: Unlock macOS Keychain" in result.output
    assert "Paste the entire callback" not in result.output
    assert not opened
    assert not container.requests
    assert container.closed


def test_failed_save_does_not_claim_authorization_or_start_sync(
    container: ConnectContainer,
) -> None:
    container.token_store.save_error = CredentialStoreError("Connection could not be saved.")
    result = CliRunner().invoke(cli.app, ["auth-connect", "--no-browser"], input=CALLBACK + "\n")
    assert result.exit_code == 1
    assert "Connection could not be saved" in result.output
    assert "authorization is saved" not in result.output
    assert "dummy-access" not in result.output
    assert not container.synced
    assert container.token_store.token is None
    assert container.closed


def test_initial_sync_failure_explains_login_was_saved(container: ConnectContainer) -> None:
    container.sync_error = BrokerRequestError("Schwab could not be reached.")
    result = CliRunner().invoke(cli.app, ["auth-connect", "--no-browser"], input=CALLBACK + "\n")
    assert result.exit_code == 1
    assert "authorization is saved" in result.output
    assert "first sync could not complete" in result.output
    assert "sync` from the project folder" in result.output
    assert "First sync complete:" not in result.output
    assert container.token_store.token is not None
    assert container.closed
