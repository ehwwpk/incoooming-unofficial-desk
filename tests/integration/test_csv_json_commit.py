from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from fastapi.testclient import TestClient

from schwab_dashboard.app import create_app
from schwab_dashboard.cli import _alembic_config
from schwab_dashboard.config import Settings
from schwab_dashboard.container import Container

POSITIONS = (
    "Account,Symbol,Description,Quantity,Last Price,Market Value,Average Price\n"
    "Fictional,CVX,Chevron,100,195.00,19500.00,150.00\n"
    "Fictional,CVX  260821C00205000,CVX call,-1,1.25,-125.00,2.00\n"
).encode("utf-16")
ACTIVITY = (
    b"Account,Date,Action,Symbol,Description,Quantity,Price,Fees,Amount\n"
    b"Fictional,08/01/2026,Sell to Open,CVX  260821C00205000,CVX call,1,1.25,0.03,124.97\n"
)


@contextmanager
def csv_client(
    tmp_path: Path, *, demo_mode: bool = False
) -> Iterator[tuple[TestClient, Container]]:
    settings = Settings(_env_file=None, data_dir=tmp_path, demo_mode=demo_mode)
    command.upgrade(_alembic_config(settings), "head")
    container = Container(settings)
    try:
        with TestClient(create_app(container), base_url="http://127.0.0.1:8182") as client:
            yield client, container
    finally:
        container.close()


def uploads(activity: bytes = ACTIVITY) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        ("files", ("positions-utf16.csv", POSITIONS, "text/csv")),
        ("files", ("activity.csv", activity, "text/csv")),
    ]


def test_json_commit_preserves_reviewed_bytes_and_selects_the_saved_book(tmp_path: Path) -> None:
    with csv_client(tmp_path) as (client, container):
        fields = {"dataset_name": "Fictional mixed encodings", "broker": "generic"}
        preview = client.post("/sources/csv/preview", data=fields, files=uploads())
        assert preview.status_code == 200
        assert preview.json()["can_commit"] is True
        response = client.post(
            "/sources/csv",
            headers={"accept": "application/json"},
            data={**fields, "preview_fingerprint": preview.json()["fingerprint"]},
            files=uploads(),
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True, "redirect": "/"}
        assert "incoooming_source=csv:" in response.headers["set-cookie"]
        assert "HttpOnly" in response.headers["set-cookie"]
        dashboard = client.get("/api/v1/dashboard").json()
        assert dashboard["mode"] == "csv"
        assert dashboard["portfolio"]["total_value"] == "19375.00"
        datasets = container.source_store.list_datasets()
        assert len(datasets) == 1
        assert datasets[0].position_count == 2
        assert datasets[0].activity_count == 1


def test_json_commit_rejects_changed_bytes_without_saving_or_switching_books(
    tmp_path: Path,
) -> None:
    with csv_client(tmp_path) as (client, container):
        fields = {"dataset_name": "Fictional review", "broker": "generic"}
        preview = client.post("/sources/csv/preview", data=fields, files=uploads()).json()
        response = client.post(
            "/sources/csv",
            headers={"accept": "application/json"},
            data={**fields, "preview_fingerprint": preview["fingerprint"]},
            files=uploads(ACTIVITY.replace(b"124.97", b"125.97")),
        )
        assert response.status_code == 422
        assert response.json()["ok"] is False
        assert response.json()["error"]
        assert "set-cookie" not in response.headers
        assert container.source_store.list_datasets() == ()


def test_standalone_demo_rejects_json_commit_without_creating_a_live_book(tmp_path: Path) -> None:
    with csv_client(tmp_path, demo_mode=True) as (client, container):
        response = client.post(
            "/sources/csv",
            headers={"accept": "application/json"},
            data={
                "dataset_name": "Fictional review",
                "broker": "generic",
                "preview_fingerprint": "not-an-approval",
            },
            files=uploads(),
        )
        assert response.status_code == 409
        assert response.json()["ok"] is False
        assert "run-local" in response.json()["error"]
        assert "set-cookie" not in response.headers
        assert container.source_store.list_datasets() == ()
        assert not (tmp_path / "schwab-ledger.sqlite3").exists()
