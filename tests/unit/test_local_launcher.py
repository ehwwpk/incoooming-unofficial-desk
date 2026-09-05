from __future__ import annotations

import errno
import socket
from pathlib import Path

import pytest
from typer.testing import CliRunner

from schwab_dashboard import cli
from schwab_dashboard.config import Settings
from schwab_dashboard.infrastructure.runtime.launcher import LocalServerError, local_listener


def test_reservation_prevents_a_second_listener_and_releases_on_failure() -> None:
    with pytest.raises(RuntimeError, match="startup failed"):
        with local_listener("127.0.0.1", 0) as listener:
            port = listener.getsockname()[1]
            with pytest.raises(LocalServerError, match="already in use"):
                with local_listener("127.0.0.1", port):
                    pytest.fail("the already reserved port was reused")
            raise RuntimeError("startup failed")

    with local_listener("127.0.0.1", port) as restarted:
        assert restarted.getsockname()[1] == port


def test_localhost_reserves_the_loopback_ipv4_address() -> None:
    with local_listener("localhost", 0) as listener:
        assert listener.getsockname()[0] == "127.0.0.1"


def test_permission_failure_has_a_useful_message(monkeypatch) -> None:
    def rejected_bind(self, address):
        raise OSError(errno.EACCES, "denied")

    monkeypatch.setattr(socket.socket, "bind", rejected_bind)
    with pytest.raises(LocalServerError, match="network permissions"):
        with local_listener("127.0.0.1", 8182):
            pytest.fail("the denied address was opened")


@pytest.mark.parametrize("command", ["serve", "demo"])
def test_occupied_port_stops_before_migrations_or_container_creation(
    command: str, monkeypatch, tmp_path: Path
) -> None:
    data_dir = tmp_path / "untouched ledger"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as unrelated:
        unrelated.bind(("127.0.0.1", 0))
        unrelated.listen(1)
        port = unrelated.getsockname()[1]

        def settings_factory(**kwargs):
            return Settings(_env_file=None, data_dir=data_dir, port=port, **kwargs)

        monkeypatch.setattr(cli, "Settings", settings_factory)
        monkeypatch.setattr(
            cli, "_upgrade_database", lambda *args, **kwargs: pytest.fail("migration ran")
        )
        monkeypatch.setattr(
            cli, "Container", lambda *args, **kwargs: pytest.fail("container was created")
        )

        result = CliRunner().invoke(cli.app, [command])

        assert result.exit_code == 1
        assert f"Port {port} is already in use" in result.output
        assert "Nothing was stopped and no database was changed" in result.output
        assert "Traceback" not in result.output
        assert not data_dir.exists()
        assert unrelated.fileno() != -1


@pytest.mark.parametrize("command", ["serve", "demo"])
def test_failed_migration_releases_the_reserved_port(
    command: str, monkeypatch, tmp_path: Path
) -> None:
    with local_listener("127.0.0.1", 0) as available:
        port = available.getsockname()[1]

    def settings_factory(**kwargs):
        return Settings(_env_file=None, data_dir=tmp_path, port=port, **kwargs)

    def failed_upgrade(*args, **kwargs):
        with pytest.raises(LocalServerError, match="already in use"):
            with local_listener("127.0.0.1", port):
                pytest.fail("migration did not retain the port reservation")
        raise RuntimeError("migration failed")

    monkeypatch.setattr(cli, "Settings", settings_factory)
    monkeypatch.setattr(cli, "_upgrade_database", failed_upgrade)
    result = CliRunner().invoke(cli.app, [command])

    assert result.exit_code == 1
    assert str(result.exception) == "migration failed"
    with local_listener("127.0.0.1", port):
        pass
