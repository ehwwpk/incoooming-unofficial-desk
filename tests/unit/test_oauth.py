from __future__ import annotations

from base64 import b64decode
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from schwab_dashboard.application.errors import AuthenticationRequiredError, BrokerRequestError
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
        app_secret="app-secret",  # pragma: allowlist secret
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
        assert request.headers["accept"] == "application/json"
        assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
        scheme, encoded_credentials = request.headers["authorization"].split(" ", 1)
        assert scheme == "Basic"
        assert b64decode(encoded_credentials).decode() == "app-key:app-secret"
        form = parse_qs(request.content.decode())
        assert form == {
            "grant_type": ["authorization_code"],
            "code": ["abc@123"],
            "redirect_uri": ["https://127.0.0.1:8182/"],
        }
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


def test_authorization_url_uses_the_exact_configured_callback() -> None:
    oauth, client = _oauth(httpx.MockTransport(lambda _: httpx.Response(500)), MemoryTokenStore())
    try:
        parsed = urlparse(oauth.authorization_url())
    finally:
        client.close()

    assert parsed.scheme == "https"
    assert parsed.netloc == "api.example"
    assert parsed.path == "/oauth/authorize"
    assert parse_qs(parsed.query) == {
        "client_id": ["app-key"],
        "redirect_uri": ["https://127.0.0.1:8182/"],
    }


def test_callback_exchange_rejects_a_different_origin_before_token_request() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    oauth, client = _oauth(httpx.MockTransport(handler), MemoryTokenStore())
    try:
        with pytest.raises(AuthenticationRequiredError) as caught:
            oauth.exchange_callback_url("https://localhost:8182/?code=abc%40123")
    finally:
        client.close()

    assert "does not match" in str(caught.value)
    assert called is False


def test_callback_exchange_rejects_duplicate_codes_before_token_request() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    oauth, client = _oauth(httpx.MockTransport(handler), MemoryTokenStore())
    try:
        with pytest.raises(AuthenticationRequiredError) as caught:
            oauth.exchange_callback_url("https://127.0.0.1:8182/?code=first&code=second")
    finally:
        client.close()

    assert "exactly one" in str(caught.value)
    assert called is False


def test_callback_exchange_does_not_echo_provider_callback_detail() -> None:
    oauth, client = _oauth(httpx.MockTransport(lambda _: httpx.Response(500)), MemoryTokenStore())
    try:
        with pytest.raises(AuthenticationRequiredError) as caught:
            oauth.exchange_callback_url(
                "https://127.0.0.1:8182/?error=access_denied&"
                "error_description=secret-account-detail"
            )
    finally:
        client.close()

    message = str(caught.value)
    assert "access_denied" in message
    assert "secret-account-detail" not in message


@pytest.mark.parametrize(
    "callback_url",
    (
        "https://127.0.0.1:invalid/?code=abc",
        "https://127.0.0.1:8182/?code=" + ("x" * 8_192),
    ),
)
def test_callback_exchange_rejects_malformed_or_oversized_urls(callback_url: str) -> None:
    oauth, client = _oauth(httpx.MockTransport(lambda _: httpx.Response(500)), MemoryTokenStore())
    try:
        with pytest.raises(AuthenticationRequiredError):
            oauth.exchange_callback_url(callback_url)
    finally:
        client.close()


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


def test_nested_schwab_rejection_reports_vetted_reason() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": "unsupported_token_type",
                "error_description": (
                    '400 Bad Request: "{\\"error\\":\\"invalid_grant\\",'
                    '\\"error_description\\":\\"Authorization code is invalid, '
                    'expired or revoked\\"}"'
                ),
            },
        )

    oauth, client = _oauth(httpx.MockTransport(handler), MemoryTokenStore())
    try:
        with pytest.raises(AuthenticationRequiredError) as caught:
            oauth.exchange_callback_url("https://127.0.0.1:8182/?code=spent")
    finally:
        client.close()

    message = str(caught.value)
    assert "HTTP 400, invalid_grant" in message
    assert "invalid, expired, or revoked" in message
    assert "400 Bad Request" not in message


def test_nested_schwab_rejection_identifies_bad_client_credentials() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "error": "unsupported_token_type",
                "error_description": (
                    '{"error":"invalid_client","error_description":"Invalid client authentication"}'
                ),
            },
        )

    oauth, client = _oauth(httpx.MockTransport(handler), MemoryTokenStore())
    try:
        with pytest.raises(AuthenticationRequiredError) as caught:
            oauth.exchange_callback_url("https://127.0.0.1:8182/?code=fresh")
    finally:
        client.close()

    message = str(caught.value)
    assert "HTTP 401, invalid_client" in message
    assert "rejected the app key or app secret" in message


def test_oauth_service_failure_does_not_expose_response_or_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="private provider detail")

    oauth, client = _oauth(httpx.MockTransport(handler), MemoryTokenStore())
    try:
        with pytest.raises(BrokerRequestError) as caught:
            oauth.exchange_callback_url("https://127.0.0.1:8182/?code=fresh")
    finally:
        client.close()

    message = str(caught.value)
    assert "HTTP 503" in message
    assert "private provider detail" not in message
    assert "api.example" not in message


def test_invalid_successful_oauth_payload_does_not_expose_token() -> None:
    oauth, client = _oauth(
        httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={"access_token": ["private-token"], "expires_in": 1800},
            )
        ),
        MemoryTokenStore(),
    )
    try:
        with pytest.raises(AuthenticationRequiredError) as caught:
            oauth.exchange_callback_url("https://127.0.0.1:8182/?code=fresh")
    finally:
        client.close()

    assert "invalid OAuth token response" in str(caught.value)
    assert "private-token" not in str(caught.value)
