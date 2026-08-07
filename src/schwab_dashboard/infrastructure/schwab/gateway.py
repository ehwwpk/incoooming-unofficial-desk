from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from schwab_dashboard.application.errors import BrokerPayloadError
from schwab_dashboard.application.ports.broker import BrokerAccountRecord
from schwab_dashboard.infrastructure.schwab.mapper import SchwabAccountMapper
from schwab_dashboard.infrastructure.schwab.oauth import SchwabOAuthClient


class SchwabReadOnlyTraderClient:
    """Allow-listed Trader API reads. No order methods exist on this class."""

    def __init__(
        self,
        *,
        base_url: str,
        oauth: SchwabOAuthClient,
        http_client: httpx.Client,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._oauth = oauth
        self._http = http_client

    def get_account_numbers(self) -> Sequence[Mapping[str, Any]]:
        return self._get_list("/accounts/accountNumbers")

    def get_accounts_with_positions(self) -> Sequence[Mapping[str, Any]]:
        return self._get_list("/accounts", params={"fields": "positions"})

    def _get_list(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        response = self._http.get(
            f"{self._base_url}{path}",
            params=params,
            headers=self._headers(self._oauth.access_token()),
        )
        if response.status_code == 401:
            response = self._http.get(
                f"{self._base_url}{path}",
                params=params,
                headers=self._headers(self._oauth.force_refresh()),
            )
        response.raise_for_status()
        payload: Any = response.json()
        if not isinstance(payload, list) or not all(isinstance(item, Mapping) for item in payload):
            raise BrokerPayloadError(f"Schwab returned an unexpected list shape for {path}.")
        return payload

    @staticmethod
    def _headers(access_token: str) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        }


class SchwabBrokerGateway:
    def __init__(
        self,
        *,
        client: SchwabReadOnlyTraderClient,
        mapper: SchwabAccountMapper,
    ) -> None:
        self._client = client
        self._mapper = mapper

    def fetch_accounts_with_positions(self) -> Sequence[BrokerAccountRecord]:
        account_numbers = self._client.get_account_numbers()
        accounts = self._client.get_accounts_with_positions()
        return self._mapper.map_records(account_numbers, accounts)
