from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
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

    def get_transactions(
        self,
        account_hash: str,
        *,
        start_at: datetime,
        end_at: datetime,
        transaction_types: str,
    ) -> Sequence[Mapping[str, Any]]:
        return self._get_list(
            f"/accounts/{account_hash}/transactions",
            params={
                "startDate": _api_datetime(start_at),
                "endDate": _api_datetime(end_at),
                "types": transaction_types,
            },
        )

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


class SchwabReadOnlyMarketDataClient:
    """Allow-listed Market Data reads. This client cannot place orders."""

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

    def get_quotes(self, symbols: Sequence[str]) -> Mapping[str, Any]:
        return self._get_mapping(
            "/quotes",
            params={"symbols": ",".join(symbols), "fields": "quote,reference"},
        )

    def get_option_chain(
        self,
        symbol: str,
        *,
        from_date: date,
        to_date: date,
        contract_type: str = "CALL",
        strike_count: int = 100,
    ) -> Mapping[str, Any]:
        normalized_contract_type = contract_type.strip().upper()
        if normalized_contract_type not in {"CALL", "PUT", "ALL"}:
            raise ValueError("contract_type must be CALL, PUT, or ALL")
        if not 1 <= strike_count <= 500:
            raise ValueError("strike_count must be between 1 and 500")
        return self._get_mapping(
            "/chains",
            params={
                "symbol": symbol,
                "contractType": normalized_contract_type,
                "includeUnderlyingQuote": "true",
                "strategy": "SINGLE",
                "strikeCount": str(strike_count),
                "fromDate": from_date.isoformat(),
                "toDate": to_date.isoformat(),
            },
        )

    def get_daily_price_history(self, symbol: str) -> Mapping[str, Any]:
        return self._get_mapping(
            "/pricehistory",
            params={
                "symbol": symbol,
                "periodType": "year",
                "period": "1",
                "frequencyType": "daily",
                "frequency": "1",
                "needExtendedHoursData": "false",
            },
        )

    def get_intraday_price_history(
        self,
        symbol: str,
        *,
        start_at: datetime,
        end_at: datetime,
        frequency_minutes: int = 30,
    ) -> Mapping[str, Any]:
        if frequency_minutes not in {1, 5, 10, 15, 30}:
            raise ValueError("frequency_minutes must be 1, 5, 10, 15, or 30")
        return self._get_mapping(
            "/pricehistory",
            params={
                "symbol": symbol,
                "frequencyType": "minute",
                "frequency": str(frequency_minutes),
                "startDate": str(int(start_at.timestamp() * 1000)),
                "endDate": str(int(end_at.timestamp() * 1000)),
                "needExtendedHoursData": "true",
                "needPreviousClose": "true",
            },
        )

    def _get_mapping(
        self,
        path: str,
        *,
        params: Mapping[str, str],
    ) -> Mapping[str, Any]:
        response = self._http.get(
            f"{self._base_url}{path}",
            params=params,
            headers=SchwabReadOnlyTraderClient._headers(self._oauth.access_token()),
        )
        if response.status_code == 401:
            response = self._http.get(
                f"{self._base_url}{path}",
                params=params,
                headers=SchwabReadOnlyTraderClient._headers(self._oauth.force_refresh()),
            )
        response.raise_for_status()
        payload: Any = response.json()
        if not isinstance(payload, Mapping):
            raise BrokerPayloadError(f"Schwab returned an unexpected object shape for {path}.")
        return payload


def _api_datetime(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")
