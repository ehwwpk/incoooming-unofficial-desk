from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient

from schwab_dashboard.app import create_app
from schwab_dashboard.cli import _alembic_config
from schwab_dashboard.config import Settings
from schwab_dashboard.container import Container

POSITIONS = (
    b"Account,Symbol,Description,Quantity,Last Price,Market Value,Average Price\n"
    b"Example,TEST,Fictional test shares,100,10.00,1000.00,9.00\n"
)


@pytest.fixture
def demo_container(tmp_path: Path) -> Iterator[Container]:
    settings = Settings(_env_file=None, data_dir=tmp_path, demo_mode=True, auto_sync_enabled=False)
    command.upgrade(_alembic_config(settings), "head")
    container = Container(settings)
    try:
        yield container
    finally:
        container.close()


def test_dedicated_demo_explains_how_to_use_real_data(demo_container: Container) -> None:
    with TestClient(create_app(demo_container), base_url="http://127.0.0.1") as client:
        client.cookies.set("incoooming_source", "schwab")
        gateway = client.get("/sources")
        assert gateway.status_code == 200
        assert "You're using the demo launcher." in gateway.text
        assert ".\\scripts\\run-local.cmd" in gateway.text
        assert "Ctrl+C" in gateway.text
        assert 'action="/sources/csv"' not in gateway.text
        assert 'name="source_key" value="schwab"' not in gateway.text
        selected = client.post("/sources/select", data={"source_key": "demo"})
        assert selected.status_code == 200
        assert 'data-demo-mode="true"' in selected.text


@pytest.mark.parametrize("source_key", ["schwab", "csv:some-dataset"])
def test_dedicated_demo_rejects_real_source_selection(
    demo_container: Container, source_key: str
) -> None:
    with TestClient(create_app(demo_container), base_url="http://127.0.0.1") as client:
        response = client.post("/sources/select", data={"source_key": source_key})
        assert response.status_code == 409
        assert "run-local.cmd" in response.json()["detail"]
        assert "set-cookie" not in response.headers


@pytest.mark.parametrize("path", ["/sources/csv/preview", "/sources/csv"])
def test_dedicated_demo_rejects_csv_uploads_without_storing_them(
    demo_container: Container, path: str
) -> None:
    with TestClient(create_app(demo_container), base_url="http://127.0.0.1") as client:
        response = client.post(
            path,
            data={"dataset_name": "My shares", "broker": "generic", "preview_fingerprint": "test"},
            files={"files": ("positions.csv", POSITIONS, "text/csv")},
        )
        assert response.status_code == 409
        assert "run-local.cmd" in response.text
        assert "set-cookie" not in response.headers
        assert demo_container.source_store.list_datasets() == ()


def test_normal_server_can_import_csv_while_demo_book_is_selected(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path, auto_sync_enabled=False)
    command.upgrade(_alembic_config(settings), "head")
    container = Container(settings)
    try:
        with TestClient(create_app(container), base_url="http://127.0.0.1") as client:
            client.post("/sources/select", data={"source_key": "demo"})
            gateway = client.get("/sources")
            assert 'action="/sources/csv"' in gateway.text
            assert "You're using the demo launcher." not in gateway.text
            data = {"dataset_name": "My shares", "broker": "generic"}
            files = {"files": ("positions.csv", POSITIONS, "text/csv")}
            preview = client.post("/sources/csv/preview", data=data, files=files)
            assert preview.status_code == 200
            imported = client.post(
                "/sources/csv",
                data={**data, "preview_fingerprint": preview.json()["fingerprint"]},
                files=files,
            )
            assert imported.status_code == 200
            assert 'data-demo-mode="false"' in imported.text
            assert "MY SHARES" in imported.text
            selected = client.post("/sources/select", data={"source_key": "schwab"})
            assert selected.status_code == 200
            assert client.cookies.get("incoooming_source") == "schwab"
    finally:
        container.close()
