from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from schwab_dashboard.application.errors import AuthenticationRequiredError
from schwab_dashboard.application.ports.tokens import OAuthTokenSet, TokenStore


class SchwabOAuthClient:
    def __init__(
        self,
        *,
        app_key: str,
        app_secret: str,
        callback_url: str,
        authorize_url: str,
        token_url: str,
        token_store: TokenStore,
        http_client: httpx.Client,
    ) -> None:
        self._app_key = app_key
        self._app_secret = app_secret
        self._callback_url = callback_url
        self._authorize_url = authorize_url
        self._token_url = token_url
        self._token_store = token_store
        self._http = http_client

    def authorization_url(self) -> str:
        query = urlencode(
            {
                "client_id": self._app_key,
                "redirect_uri": self._callback_url,
            }
        )
        return f"{self._authorize_url}?{query}"

    def exchange_callback_url(self, callback_url: str) -> OAuthTokenSet:
        parsed = urlparse(callback_url.strip())
        query = parse_qs(parsed.query)
        if "error" in query:
            detail = query.get("error_description", query["error"])[0]
            raise AuthenticationRequiredError(f"Schwab authorization failed: {detail}")
        code_values = query.get("code")
        if not code_values or not code_values[0]:
            raise AuthenticationRequiredError(
                "The pasted callback URL does not contain an authorization code."
            )
        token = self._request_token(
            {
                "grant_type": "authorization_code",
                "code": code_values[0],
                "redirect_uri": self._callback_url,
            }
        )
        self._token_store.save(token)
        return token

    def access_token(self) -> str:
        token = self._token_store.load()
        if token is None:
            raise AuthenticationRequiredError(
                "No Schwab OAuth token is stored. Run `schwab-dashboard auth-url`, "
                "then `schwab-dashboard auth-complete`."
            )
        if token.expires_within(120):
            token = self.refresh(token)
        return token.access_token

    def force_refresh(self) -> str:
        token = self._token_store.load()
        if token is None:
            raise AuthenticationRequiredError("No Schwab OAuth token is stored.")
        return self.refresh(token).access_token

    def refresh(self, previous: OAuthTokenSet) -> OAuthTokenSet:
        if not previous.refresh_token:
            raise AuthenticationRequiredError(
                "The stored token has no refresh token. Complete Schwab authorization again."
            )
        token = self._request_token(
            {
                "grant_type": "refresh_token",
                "refresh_token": previous.refresh_token,
            },
            previous=previous,
        )
        self._token_store.save(token)
        return token

    def token_available(self) -> bool:
        return self._token_store.load() is not None

    def clear_token(self) -> None:
        self._token_store.delete()

    def _request_token(
        self,
        form: dict[str, str],
        *,
        previous: OAuthTokenSet | None = None,
    ) -> OAuthTokenSet:
        response = self._http.post(
            self._token_url,
            data=form,
            auth=httpx.BasicAuth(self._app_key, self._app_secret),
            headers={"Accept": "application/json"},
        )
        if response.status_code in {400, 401}:
            raise AuthenticationRequiredError(
                "Schwab rejected the OAuth token request. The authorization code may be "
                "expired, the callback URL may not match exactly, or re-authorization "
                "may be required."
            )
        response.raise_for_status()
        payload: Any = response.json()
        if not isinstance(payload, dict):
            raise AuthenticationRequiredError("Schwab returned an unexpected OAuth response shape.")
        return OAuthTokenSet.from_oauth_response(payload, previous=previous)
