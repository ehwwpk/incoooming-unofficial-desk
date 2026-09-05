from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from schwab_dashboard.application.errors import AuthenticationRequiredError, BrokerRequestError
from schwab_dashboard.application.ports.tokens import OAuthTokenSet, TokenStore
from schwab_dashboard.infrastructure.runtime.platform_commands import dashboard_command

MAX_CALLBACK_URL_LENGTH = 8_192


def _nested_oauth_payload(value: object) -> dict[str, object] | None:
    """Return a nested OAuth error object without exposing arbitrary provider text."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None

    candidates = [value]
    left = value.find("{")
    right = value.rfind("}")
    if left >= 0 and right > left:
        nested_slice = value[left : right + 1]
        candidates.extend((nested_slice, nested_slice.replace('\\"', '"')))

    for candidate in candidates:
        for _ in range(2):
            try:
                parsed = json.loads(candidate)
            except (json.JSONDecodeError, TypeError):
                break
            if isinstance(parsed, dict):
                return parsed
            if not isinstance(parsed, str):
                break
            candidate = parsed
    return None


def _safe_oauth_rejection(payload: object) -> tuple[str, str | None]:
    """Extract Schwab's machine code and a vetted diagnostic, never raw request data."""
    if not isinstance(payload, dict):
        return "unknown_oauth_error", None

    provider_error = payload.get("error")
    if not (isinstance(provider_error, str) and provider_error.replace("_", "").isalnum()):
        provider_error = "unknown_oauth_error"

    nested = _nested_oauth_payload(payload.get("error_description"))
    if nested is not None:
        nested_error = nested.get("error")
        if isinstance(nested_error, str) and nested_error.replace("_", "").isalnum():
            provider_error = nested_error

    descriptions: list[str] = []
    for candidate in (
        nested.get("error_description") if nested else None,
        payload.get("error_description"),
    ):
        if isinstance(candidate, str):
            descriptions.append(candidate.casefold())
    joined = " ".join(descriptions)

    if "authorization code" in joined and any(
        word in joined for word in ("invalid", "expired", "revoked")
    ):
        return provider_error, "Schwab says the authorization code is invalid, expired, or revoked."
    if "bad authorization code" in joined or "malformed" in joined:
        return provider_error, "Schwab says the authorization code is malformed."
    if "invalid client" in joined or "client authentication" in joined:
        return provider_error, "Schwab rejected the app key or app secret."
    if "redirect" in joined and ("invalid" in joined or "mismatch" in joined):
        return provider_error, "Schwab says the callback URL does not match the app registration."
    if "refresh token" in joined and any(
        word in joined for word in ("invalid", "expired", "revoked", "authentication")
    ):
        return provider_error, "Schwab says the stored refresh token is no longer valid."
    return provider_error, None


def _callback_target(value: str) -> tuple[str, str, int | None, str]:
    """Return the origin and path Schwab must redirect to, excluding one-time query data."""
    parsed = urlparse(value.strip())
    scheme = parsed.scheme.casefold()
    hostname = (parsed.hostname or "").casefold()
    default_port = 443 if scheme == "https" else 80 if scheme == "http" else None
    return scheme, hostname, parsed.port or default_port, parsed.path or "/"


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
        normalized_callback = callback_url.strip()
        if len(normalized_callback) > MAX_CALLBACK_URL_LENGTH:
            raise AuthenticationRequiredError("The pasted callback URL is too long.")
        try:
            parsed = urlparse(normalized_callback)
            supplied_target = _callback_target(normalized_callback)
            configured_target = _callback_target(self._callback_url)
            query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=16)
        except ValueError as exc:
            raise AuthenticationRequiredError("The pasted callback URL is malformed.") from exc
        if supplied_target != configured_target:
            raise AuthenticationRequiredError(
                "The callback URL does not match this app's configured Schwab callback."
            )
        if "error" in query:
            callback_payload: dict[str, object] = {"error": query["error"][0]}
            descriptions = query.get("error_description")
            if descriptions:
                callback_payload["error_description"] = descriptions[0]
            provider_error, safe_detail = _safe_oauth_rejection(callback_payload)
            detail = f" {safe_detail}" if safe_detail else " Try authorizing again."
            raise AuthenticationRequiredError(
                f"Schwab authorization failed ({provider_error}).{detail}"
            )
        code_values = query.get("code")
        if not code_values:
            raise AuthenticationRequiredError(
                "The pasted callback URL does not contain an authorization code."
            )
        if len(code_values) != 1 or not code_values[0]:
            raise AuthenticationRequiredError(
                "The pasted callback URL must contain exactly one authorization code."
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
                "No Schwab OAuth token is stored. From the project folder, run "
                f"`{dashboard_command('auth-connect')}` to connect."
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
        try:
            response = self._http.post(
                self._token_url,
                data=form,
                auth=httpx.BasicAuth(self._app_key, self._app_secret),
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise BrokerRequestError("Schwab's OAuth service could not be reached.") from exc
        if response.status_code in {400, 401}:
            provider_error = "unknown_oauth_error"
            safe_detail: str | None = None
            try:
                provider_error, safe_detail = _safe_oauth_rejection(response.json())
            except (ValueError, TypeError):
                pass
            detail = (
                f" {safe_detail}"
                if safe_detail
                else " The authorization code may be expired or consumed, the callback URL may "
                "not match exactly, or the app credentials may need review."
            )
            raise AuthenticationRequiredError(
                "Schwab rejected the OAuth token request "
                f"(HTTP {response.status_code}, {provider_error}).{detail}"
            )
        if response.is_error:
            raise BrokerRequestError(
                f"Schwab's OAuth service failed (HTTP {response.status_code})."
            )
        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise AuthenticationRequiredError(
                "Schwab returned an unreadable OAuth response."
            ) from exc
        if not isinstance(payload, dict):
            raise AuthenticationRequiredError("Schwab returned an unexpected OAuth response shape.")
        try:
            return OAuthTokenSet.from_oauth_response(payload, previous=previous)
        except (TypeError, ValueError) as exc:
            raise AuthenticationRequiredError(
                "Schwab returned an invalid OAuth token response."
            ) from exc
