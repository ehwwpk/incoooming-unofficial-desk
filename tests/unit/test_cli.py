from contextlib import contextmanager
from pathlib import Path

from schwab_dashboard import cli
from schwab_dashboard.config import Settings


def test_serve_upgrades_the_selected_database_before_starting(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)
    calls: list[object] = []
    listener = object()

    @contextmanager
    def reserve(host, port):
        calls.append(("reserve", host, port))
        yield listener
        calls.append("released")

    class FakeServer:
        def __init__(self, config):
            self.config = config

        def run(self, *, sockets):
            calls.append(("run", self.config, sockets))

    monkeypatch.setattr(cli, "Settings", lambda: settings)
    monkeypatch.setattr(cli, "local_listener", reserve)
    monkeypatch.setattr(
        cli,
        "_upgrade_database",
        lambda selected, *, announce: calls.append(("upgrade", selected, announce)),
    )
    monkeypatch.setattr(cli, "create_app", lambda: "app")
    monkeypatch.setattr(cli.uvicorn, "Server", FakeServer)

    cli.serve()

    assert calls[0] == ("reserve", settings.host, settings.port)
    assert calls[1] == ("upgrade", settings, False)
    assert calls[2][0] == "run"
    assert calls[2][1].app == "app"
    assert calls[2][1].host == settings.host
    assert calls[2][1].port == settings.port
    assert calls[2][1].log_level == "info"
    assert calls[2][2] == [listener]
    assert calls[-1] == "released"


def test_demo_upgrades_an_isolated_database_before_starting(monkeypatch, tmp_path: Path) -> None:
    calls: list[object] = []
    listener = object()

    @contextmanager
    def reserve(host, port):
        calls.append(("reserve", host, port))
        yield listener
        calls.append("released")

    def settings_factory(*, demo_mode: bool = False) -> Settings:
        return Settings(_env_file=None, data_dir=tmp_path, demo_mode=demo_mode)

    class FakeContainer:
        def __init__(self, settings: Settings) -> None:
            calls.append(("container", settings))

        def close(self) -> None:
            calls.append("closed")

    class FakeServer:
        def __init__(self, config):
            pass

        def run(self, *, sockets):
            calls.append(("run", sockets))

    monkeypatch.setattr(cli, "Settings", settings_factory)
    monkeypatch.setattr(cli, "local_listener", reserve)
    monkeypatch.setattr(
        cli,
        "_upgrade_database",
        lambda selected, *, announce: calls.append(("upgrade", selected, announce)),
    )
    monkeypatch.setattr(cli, "Container", FakeContainer)
    monkeypatch.setattr(cli, "create_app", lambda container: ("app", container))
    monkeypatch.setattr(cli.uvicorn, "Server", FakeServer)

    cli.demo()

    assert calls[0] == ("reserve", "127.0.0.1", 8182)
    upgraded = calls[1]
    assert isinstance(upgraded, tuple)
    assert upgraded[0] == "upgrade"
    demo_settings = upgraded[1]
    assert isinstance(demo_settings, Settings)
    assert demo_settings.database_url.endswith("/demo-ledger.sqlite3")
    assert calls[-3] == ("run", [listener])
    assert calls[-2:] == ["closed", "released"]
