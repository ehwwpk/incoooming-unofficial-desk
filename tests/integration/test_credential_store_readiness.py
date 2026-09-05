from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from schwab_dashboard.app import create_app
from schwab_dashboard.application.errors import CredentialStoreError
from schwab_dashboard.application.ports.tokens import OAuthTokenSet
from schwab_dashboard.cli import app as cli_app
from schwab_dashboard.config import Settings
from schwab_dashboard.container import Container
from schwab_dashboard.infrastructure.database.tables import Base
from schwab_dashboard.infrastructure.secrets.keyring_tokens import KeyringTokenStore


def test_csv_gateway_and_sync_status_survive_locked_storage_and_recover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    locked = True

    def load(store: KeyringTokenStore) -> OAuthTokenSet | None:
        if locked:
            raise CredentialStoreError("Unlock macOS Keychain and retry.")
        return OAuthTokenSet(access_token="dummy-access")

    monkeypatch.setattr(KeyringTokenStore, "load", load)
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        schwab_app_key="dummy-key",
        schwab_app_secret="dummy-secret",
        auto_sync_enabled=False,
    )
    container = Container(settings)
    Base.metadata.create_all(container.engine)
    try:
        assert not container.token_available()
        assert container.credential_store_error == "Unlock macOS Keychain and retry."
        with TestClient(create_app(container), base_url="http://127.0.0.1") as client:
            assert client.get("/sources").status_code == 200
            response = client.get("/api/v1/sync/status")
            assert response.status_code == 200
            assert response.json()["state"] == "authorization_required"
            locked = False
            response = client.get("/api/v1/sync/status")
            assert response.json()["token_available"]
            assert container.credential_store_error is None
    finally:
        container.close()


def test_doctor_reports_credential_storage_failure_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def load(store: KeyringTokenStore) -> OAuthTokenSet | None:
        raise CredentialStoreError("Unlock macOS Keychain and retry.")

    monkeypatch.setattr(KeyringTokenStore, "load", load)
    result = CliRunner().invoke(
        cli_app,
        ["doctor"],
        env={
            "SCHWAB_APP_KEY": "dummy-key",
            "SCHWAB_APP_SECRET": "dummy-secret",
            "SCHWAB_DASHBOARD_DATA_DIR": str(tmp_path),
            "SCHWAB_DASHBOARD_DEMO_MODE": "false",
        },
    )
    assert result.exit_code == 1
    assert "Not ready: Unlock macOS Keychain" in result.output
    assert "Schwab token available: False" in result.output
    assert "Traceback" not in result.output
    assert "dummy-secret" not in result.output


def test_cached_dashboard_follows_unlock_and_logout_without_reading_keychain_during_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    available = False
    reads = 0

    def load(store: KeyringTokenStore) -> OAuthTokenSet | None:
        nonlocal reads
        reads += 1
        return OAuthTokenSet(access_token="dummy-access") if available else None

    def delete(store: KeyringTokenStore) -> None:
        nonlocal available
        available = False

    monkeypatch.setattr(KeyringTokenStore, "load", load)
    monkeypatch.setattr(KeyringTokenStore, "delete", delete)
    container = Container(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            schwab_app_key="dummy-key",
            schwab_app_secret="dummy-secret",
            auto_sync_enabled=False,
        )
    )
    Base.metadata.create_all(container.engine)
    try:
        assert reads == 1
        reader = container.read_dashboard("schwab")
        disconnected = reader.execute()
        assert not disconnected.token_available
        assert reader.execute() is disconnected
        assert reads == 1

        available = True
        assert container.token_available()
        connected = reader.execute()
        assert connected.token_available
        assert connected is not disconnected
        assert reads == 2
        with TestClient(create_app(container), base_url="http://127.0.0.1") as client:
            client.post("/sources/select", data={"source_key": "schwab"})
            assert client.get("/").status_code == 200
            assert reads == 2

        container.token_store.delete()
        assert not container.token_available()
        logged_out = reader.execute()
        assert not logged_out.token_available
        assert logged_out is not connected
        assert reads == 3
    finally:
        container.close()
