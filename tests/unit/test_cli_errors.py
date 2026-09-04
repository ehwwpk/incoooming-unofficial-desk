from pathlib import Path

from typer.testing import CliRunner

from schwab_dashboard.cli import app


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
