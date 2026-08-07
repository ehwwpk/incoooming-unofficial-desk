from __future__ import annotations

import httpx

from schwab_dashboard.infrastructure.schwab.gateway import SchwabReadOnlyTraderClient


class StubOAuth:
    def __init__(self) -> None:
        self.refresh_count = 0

    def access_token(self) -> str:
        return "initial-token"

    def force_refresh(self) -> str:
        self.refresh_count += 1
        return "refreshed-token"


def test_trader_client_exposes_only_get_requests() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[])

    oauth = StubOAuth()
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = SchwabReadOnlyTraderClient(
            base_url="https://broker.test/trader/v1",
            oauth=oauth,  # type: ignore[arg-type]
            http_client=http_client,
        )
        client.get_account_numbers()
        client.get_accounts_with_positions()

    assert [request.method for request in requests] == ["GET", "GET"]
    assert [request.url.path for request in requests] == [
        "/trader/v1/accounts/accountNumbers",
        "/trader/v1/accounts",
    ]
    assert requests[1].url.params["fields"] == "positions"


def test_trader_client_retries_one_unauthorized_response_after_refresh() -> None:
    authorization_headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        authorization_headers.append(request.headers["Authorization"])
        if len(authorization_headers) == 1:
            return httpx.Response(401, json={"error": "expired"})
        return httpx.Response(200, json=[])

    oauth = StubOAuth()
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = SchwabReadOnlyTraderClient(
            base_url="https://broker.test/trader/v1",
            oauth=oauth,  # type: ignore[arg-type]
            http_client=http_client,
        )
        assert client.get_account_numbers() == []

    assert oauth.refresh_count == 1
    assert authorization_headers == ["Bearer initial-token", "Bearer refreshed-token"]
