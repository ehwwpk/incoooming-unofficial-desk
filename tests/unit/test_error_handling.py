from __future__ import annotations

import asyncio

from starlette.requests import Request

from schwab_dashboard.api.errors import unhandled_exception


def _request(*, accept: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/broken",
            "raw_path": b"/broken",
            "query_string": b"",
            "headers": [(b"accept", accept.encode("ascii"))],
            "client": ("127.0.0.1", 50000),
            "server": ("127.0.0.1", 8182),
        }
    )


def test_unhandled_exception_renders_recoverable_html_without_exception_details() -> None:
    response = asyncio.run(
        unhandled_exception(
            _request(accept="text/html"),
            RuntimeError("secret diagnostic detail"),
        )
    )

    body = response.body.decode("utf-8")
    assert response.status_code == 500
    assert "This page tripped over a wire" in body
    assert "restart-local.cmd" in body
    assert "secret diagnostic detail" not in body


def test_unhandled_exception_returns_generic_json_for_api_clients() -> None:
    response = asyncio.run(
        unhandled_exception(
            _request(accept="application/json"),
            RuntimeError("secret diagnostic detail"),
        )
    )

    assert response.status_code == 500
    assert b'"status":"error"' in response.body
    assert b"secret diagnostic detail" not in response.body
