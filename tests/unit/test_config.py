from pathlib import Path

from schwab_dashboard.config import Settings


def test_database_path_is_derived_from_data_directory(tmp_path: Path) -> None:
    settings = Settings(SCHWAB_DASHBOARD_DATA_DIR=tmp_path)

    assert settings.database_url.endswith("/schwab-ledger.sqlite3")
    assert settings.resolved_data_dir == tmp_path.resolve()


def test_credentials_are_never_required_for_local_dashboard_startup() -> None:
    settings = Settings(SCHWAB_APP_KEY=None, SCHWAB_APP_SECRET=None)

    assert settings.schwab_credentials_configured is False


def test_blank_credentials_are_not_treated_as_configured() -> None:
    settings = Settings(SCHWAB_APP_KEY="  ", SCHWAB_APP_SECRET="")

    assert settings.schwab_credentials_configured is False


def test_demo_mode_is_explicit_and_disabled_by_default() -> None:
    assert Settings(_env_file=None).demo_mode is False
    assert Settings(_env_file=None, demo_mode=True).demo_mode is True
