from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from schwab_dashboard.application.errors import AuthenticationRequiredError
from schwab_dashboard.application.ports.tokens import OAuthTokenSet
from schwab_dashboard.infrastructure.schwab.oauth import SchwabOAuthClient
from tests.fakes import MemoryTokenStore


def _oauth(
    handler: httpx.MockTransport,
    store: MemoryTokenStore,
) -> tuple[SchwabOAuthClient, httpx.Client]:
    client = httpx.Client(transport=handler)
    oauth = SchwabOAuthClient(
        app_key="app-key",
        app_secret="app-secret",
        callback_url="https://127.0.0.1:8182/",
        authorize_url="https://api.example/oauth/authorize",
        token_url="https://api.example/oauth/token",
        token_store=store,
        http_client=client,
    )
    return oauth, client


def test_callback_exchange_stores_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/oauth/token"
        return httpx.Response(
            200,
            json={
                "access_token": "access-one",
                "refresh_token": "refresh-one",
                "expires_in": 1800,
            },
        )

    store = MemoryTokenStore()
    oauth, client = _oauth(httpx.MockTransport(handler), store)
    try:
        token = oauth.exchange_callback_url("https://127.0.0.1:8182/?code=abc%40123")
    finally:
        client.close()

    assert token.access_token == "access-one"
    assert store.token is not None
    assert store.token.refresh_token == "refresh-one"


def test_expired_access_token_is_refreshed_without_losing_refresh_token() -> None:
    previous = OAuthTokenSet(
        access_token="expired",
        refresh_token="refresh-original",
        expires_in=60,
        issued_at=datetime.now(UTC) - timedelta(hours=1),
        refresh_issued_at=datetime.now(UTC) - timedelta(days=1),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert b"grant_type=refresh_token" in request.content
        return httpx.Response(200, json={"access_token": "fresh", "expires_in": 1800})

    store = MemoryTokenStore(previous)
    oauth, client = _oauth(httpx.MockTransport(handler), store)
    try:
        access_token = oauth.access_token()
    finally:
        client.close()

    assert access_token == "fresh"
    assert store.token is not None
    assert store.token.refresh_token == "refresh-original"
    assert store.token.refresh_issued_at == previous.refresh_issued_at


def test_token_rejection_reports_safe_provider_code_without_description() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": "invalid_grant", "error_description": "do not echo this detail"},
        )

    oauth, client = _oauth(httpx.MockTransport(handler), MemoryTokenStore())
    try:
        with pytest.raises(AuthenticationRequiredError) as caught:
            oauth.exchange_callback_url("https://127.0.0.1:8182/?code=spent")
    finally:
        client.close()

    message = str(caught.value)
    assert "HTTP 400, invalid_grant" in message
    assert "do not echo" not in message
