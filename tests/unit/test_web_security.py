from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from fastapi import UploadFile
from pydantic import ValidationError

from schwab_dashboard.api.routes.sources import _read_csv_uploads
from schwab_dashboard.app import create_app
from schwab_dashboard.application.imports import CsvImportError
from schwab_dashboard.application.imports.csv_text import MAX_CSV_BYTES
from schwab_dashboard.config import Settings
from schwab_dashboard.container import Container


def test_server_host_accepts_only_local_ipv4_interfaces() -> None:
    assert Settings(_env_file=None, host="localhost").host == "localhost"
    assert Settings(_env_file=None, host="127.0.0.2").host == "127.0.0.2"
    for unsafe_host in ("0.0.0.0", "192.168.1.10", "example.com", "::1"):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, host=unsafe_host)


def test_local_web_rejects_untrusted_hosts_and_cross_site_writes(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path, demo_mode=True)
    container = Container(settings)

    async def exercise() -> tuple[httpx.Response, ...]:
        transport = httpx.ASGITransport(app=create_app(container))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1:8182",
            follow_redirects=False,
        ) as client:
            live = await client.get("/api/v1/health/live")
            bad_host = await client.get("/api/v1/health/live", headers={"host": "attacker.example"})
            cross_site = await client.post(
                "/sources/select",
                data={"source_key": "demo"},
                headers={
                    "origin": "https://attacker.example",
                    "sec-fetch-site": "cross-site",
                },
            )
            mismatched_origin = await client.post(
                "/sources/select",
                data={"source_key": "demo"},
                headers={
                    "origin": "http://localhost:8182",
                    "sec-fetch-site": "same-origin",
                },
            )
            same_origin = await client.post(
                "/sources/select",
                data={"source_key": "demo"},
                headers={
                    "origin": "http://127.0.0.1:8182",
                    "sec-fetch-site": "same-origin",
                },
            )
        return live, bad_host, cross_site, mismatched_origin, same_origin

    try:
        live, bad_host, cross_site, mismatched_origin, same_origin = asyncio.run(exercise())
    finally:
        container.close()

    assert live.status_code == 200
    assert live.headers["cache-control"] == "no-store"
    assert live.headers["x-content-type-options"] == "nosniff"
    assert live.headers["x-frame-options"] == "DENY"
    assert live.headers["referrer-policy"] == "same-origin"
    assert "frame-ancestors 'none'" in live.headers["content-security-policy"]
    assert bad_host.status_code == 400
    assert cross_site.status_code == 403
    assert mismatched_origin.status_code == 403
    assert same_origin.status_code == 303
    assert same_origin.headers["location"] == "/"
    assert same_origin.headers["referrer-policy"] == "same-origin"


@pytest.mark.parametrize(
    "headers",
    (
        {"origin": "null", "sec-fetch-site": "same-origin"},
        {"origin": "null", "referer": "http://127.0.0.1:8182/sources"},
        {"origin": "http://127.0.0.1:8182", "sec-fetch-site": "cross-site"},
        {"origin": "http://127.0.0.1:8183", "sec-fetch-site": "same-origin"},
        {"origin": "https://127.0.0.1:8182", "sec-fetch-site": "same-origin"},
        {"referer": "https://attacker.example/"},
    ),
)
def test_form_referrer_fix_does_not_allow_opaque_or_cross_origin_writes(
    tmp_path: Path, headers: dict[str, str]
) -> None:
    container = Container(Settings(_env_file=None, data_dir=tmp_path, demo_mode=True))

    async def exercise() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(container)),
            base_url="http://127.0.0.1:8182",
        ) as client:
            return await client.post(
                "/sources/select", data={"source_key": "demo"}, headers=headers
            )

    try:
        response = asyncio.run(exercise())
    finally:
        container.close()

    assert response.status_code == 403
    assert response.text == "Cross-site request blocked."
    assert "set-cookie" not in response.headers


def test_csv_upload_reader_caps_count_size_and_filename() -> None:
    too_many = [UploadFile(file=BytesIO(b"x"), filename=f"{index}.csv") for index in range(9)]
    with pytest.raises(CsvImportError, match="no more than eight"):
        asyncio.run(_read_csv_uploads(too_many))

    oversized = UploadFile(file=BytesIO(b"x" * (MAX_CSV_BYTES + 1)), filename="large.csv")
    with pytest.raises(CsvImportError, match="limited to 10 MB"):
        asyncio.run(_read_csv_uploads([oversized]))

    uploaded = UploadFile(file=BytesIO(b"a,b\n1,2\n"), filename=r"C:\private\positions.csv")
    assert asyncio.run(_read_csv_uploads([uploaded])) == [("positions.csv", b"a,b\n1,2\n")]
