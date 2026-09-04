from pathlib import Path

from schwab_dashboard import cli
from schwab_dashboard.config import Settings


def test_serve_upgrades_the_selected_database_before_starting(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)
    calls: list[object] = []
    monkeypatch.setattr(cli, "Settings", lambda: settings)
    monkeypatch.setattr(
        cli,
        "_upgrade_database",
        lambda selected, *, announce: calls.append(("upgrade", selected, announce)),
    )
    monkeypatch.setattr(cli, "create_app", lambda: "app")
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kwargs: calls.append((app, kwargs)))

    cli.serve()

    assert calls[0] == ("upgrade", settings, False)
    assert calls[1] == (
        "app",
        {"host": settings.host, "port": settings.port, "log_level": "info"},
    )


def test_demo_upgrades_an_isolated_database_before_starting(monkeypatch, tmp_path: Path) -> None:
    calls: list[object] = []

    def settings_factory(*, demo_mode: bool = False) -> Settings:
        return Settings(_env_file=None, data_dir=tmp_path, demo_mode=demo_mode)

    class FakeContainer:
        def __init__(self, settings: Settings) -> None:
            calls.append(("container", settings))

        def close(self) -> None:
            calls.append("closed")

    monkeypatch.setattr(cli, "Settings", settings_factory)
    monkeypatch.setattr(
        cli,
        "_upgrade_database",
        lambda selected, *, announce: calls.append(("upgrade", selected, announce)),
    )
    monkeypatch.setattr(cli, "Container", FakeContainer)
    monkeypatch.setattr(cli, "create_app", lambda container: ("app", container))
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kwargs: calls.append((app, kwargs)))

    cli.demo()

    upgraded = calls[0]
    assert isinstance(upgraded, tuple)
    assert upgraded[0] == "upgrade"
    demo_settings = upgraded[1]
    assert isinstance(demo_settings, Settings)
    assert demo_settings.database_url.endswith("/demo-ledger.sqlite3")
    assert calls[-1] == "closed"
