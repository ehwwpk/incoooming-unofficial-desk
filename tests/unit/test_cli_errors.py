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


def test_sync_reports_missing_authorization_without_traceback() -> None:
    result = CliRunner().invoke(
        app,
        ["sync"],
        env={"SCHWAB_APP_KEY": "", "SCHWAB_APP_SECRET": ""},
    )

    assert result.exit_code == 1
    assert "Not ready: Schwab app credentials are missing" in result.output
    assert "Traceback" not in result.output
