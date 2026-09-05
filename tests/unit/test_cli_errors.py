from pathlib import Path

import pytest
from typer.testing import CliRunner

from schwab_dashboard.application.errors import CredentialStoreError
from schwab_dashboard.cli import app
from schwab_dashboard.infrastructure.secrets.keyring_tokens import KeyringTokenStore


def test_auth_url_reports_blank_credentials_without_traceback() -> None:
    result = CliRunner().invoke(
        app,
        ["auth-url"],
        env={"SCHWAB_APP_KEY": "", "SCHWAB_APP_SECRET": ""},
    )

    assert result.exit_code == 1
    assert "Not ready: Schwab app credentials are missing" in result.output
    assert "Traceback" not in result.output
    assert "client_id=" not in result.output


def test_sync_reports_missing_authorization_without_traceback(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        ["sync"],
        env={
            "SCHWAB_APP_KEY": "",
            "SCHWAB_APP_SECRET": "",
            "SCHWAB_DASHBOARD_DATA_DIR": str(tmp_path),
        },
    )

    assert result.exit_code == 1
    assert "Not ready: Schwab app credentials are missing" in result.output
    assert "Traceback" not in result.output


def test_auth_complete_from_stdin_requires_a_callback() -> None:
    result = CliRunner().invoke(app, ["auth-complete", "--from-stdin"], input="")

    assert result.exit_code == 1
    assert "no callback URL was received" in result.output
    assert "Traceback" not in result.output


def test_auth_clear_works_after_app_credentials_are_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    removed: list[bool] = []
    monkeypatch.setattr(KeyringTokenStore, "delete", lambda store: removed.append(True))
    result = CliRunner().invoke(
        app,
        ["auth-clear"],
        env={
            "SCHWAB_APP_KEY": "",
            "SCHWAB_APP_SECRET": "",
            "SCHWAB_DASHBOARD_DATA_DIR": str(tmp_path),
        },
    )
    assert result.exit_code == 0
    assert removed == [True]
    assert "OAuth token removed" in result.output


def test_auth_clear_reports_failed_deletion_without_claiming_logout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(store: KeyringTokenStore) -> None:
        raise CredentialStoreError("Connection could not be removed from macOS Keychain.")

    monkeypatch.setattr(KeyringTokenStore, "delete", denied)
    result = CliRunner().invoke(
        app,
        ["auth-clear"],
        env={
            "SCHWAB_APP_KEY": "",
            "SCHWAB_APP_SECRET": "",
            "SCHWAB_DASHBOARD_DATA_DIR": str(tmp_path),
        },
    )
    assert result.exit_code == 1
    assert "could not be removed" in result.output
    assert "OAuth token removed" not in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize("command", ["auth-connect", "auth-clear"])
def test_demo_mode_auth_commands_explain_how_to_leave_demo_without_reading_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    def unexpected_access(store: KeyringTokenStore) -> None:
        raise AssertionError("Dedicated demo must not access real credential storage")

    monkeypatch.setattr(KeyringTokenStore, "load", unexpected_access)
    monkeypatch.setattr(KeyringTokenStore, "delete", unexpected_access)
    result = CliRunner().invoke(
        app,
        [command],
        env={
            "SCHWAB_APP_KEY": "dummy-key",
            "SCHWAB_APP_SECRET": "dummy-secret",
            "SCHWAB_DASHBOARD_DEMO_MODE": "true",
            "SCHWAB_DASHBOARD_DATA_DIR": str(tmp_path),
        },
    )
    assert result.exit_code == 1
    assert "SCHWAB_DASHBOARD_DEMO_MODE is true" in result.output
    assert "Set it to false" in result.output
    assert "Paste the entire callback" not in result.output
    assert "Traceback" not in result.output
