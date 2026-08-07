from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from schwab_dashboard.application.errors import BrokerPayloadError
from schwab_dashboard.application.ports.broker import BrokerAccountRecord
from schwab_dashboard.domain.broker import BrokerAccount, BrokerPosition


class SchwabAccountMapper:
    def map_records(
        self,
        account_numbers_payload: Sequence[Mapping[str, Any]],
        accounts_payload: Sequence[Mapping[str, Any]],
    ) -> tuple[BrokerAccountRecord, ...]:
        account_hashes = self._account_hashes(account_numbers_payload)
        records: list[BrokerAccountRecord] = []

        for wrapper in accounts_payload:
            securities_account = wrapper.get("securitiesAccount")
            if not isinstance(securities_account, Mapping):
                raise BrokerPayloadError("Schwab account payload is missing securitiesAccount.")

            visible_number = self._required_text(securities_account, "accountNumber")
            external_key = account_hashes.get(visible_number)
            if external_key is None:
                raise BrokerPayloadError(
                    "A returned Schwab account could not be matched to its account hash."
                )

            positions_payload = securities_account.get("positions") or []
            if not isinstance(positions_payload, Sequence) or isinstance(
                positions_payload, (str, bytes)
            ):
                raise BrokerPayloadError("Schwab positions payload is not a list.")

            positions = tuple(self._map_position(position) for position in positions_payload)
            records.append(
                BrokerAccountRecord(
                    account=BrokerAccount(
                        external_key=external_key,
                        account_mask=self._mask_account(visible_number),
                        account_type=str(securities_account.get("type") or "UNKNOWN"),
                    ),
                    positions=positions,
                    raw_payload=dict(wrapper),
                )
            )

        return tuple(records)

    def _map_position(self, payload: Any) -> BrokerPosition:
        if not isinstance(payload, Mapping):
            raise BrokerPayloadError("A Schwab position row is not an object.")
        instrument = payload.get("instrument")
        if not isinstance(instrument, Mapping):
            raise BrokerPayloadError("A Schwab position is missing its instrument.")

        symbol = self._required_text(instrument, "symbol").strip()
        instrument_key = str(instrument.get("cusip") or symbol).strip()
        asset_type = str(instrument.get("assetType") or "UNKNOWN").strip()

        return BrokerPosition(
            instrument_key=instrument_key,
            symbol=symbol,
            asset_type=asset_type,
            long_quantity=self._decimal(payload.get("longQuantity"), default=Decimal("0")),
            short_quantity=self._decimal(payload.get("shortQuantity"), default=Decimal("0")),
            average_price=self._optional_decimal(payload.get("averagePrice")),
            market_value=self._optional_decimal(payload.get("marketValue")),
            day_profit_loss=self._optional_decimal(payload.get("currentDayProfitLoss")),
            day_profit_loss_percent=self._optional_decimal(
                payload.get("currentDayProfitLossPercentage")
            ),
        )

    @staticmethod
    def _account_hashes(payload: Sequence[Mapping[str, Any]]) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in payload:
            account_number = item.get("accountNumber")
            hash_value = item.get("hashValue")
            if not account_number or not hash_value:
                raise BrokerPayloadError(
                    "Schwab account-number response is missing accountNumber or hashValue."
                )
            result[str(account_number)] = str(hash_value)
        return result

    @staticmethod
    def _required_text(payload: Mapping[str, Any], field: str) -> str:
        value = payload.get(field)
        if value is None or not str(value).strip():
            raise BrokerPayloadError(f"Schwab payload is missing required field: {field}")
        return str(value)

    @staticmethod
    def _mask_account(account_number: str) -> str:
        return f"...{account_number[-4:]}"

    @staticmethod
    def _decimal(value: Any, *, default: Decimal) -> Decimal:
        if value is None:
            return default
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise BrokerPayloadError("Schwab returned a non-numeric quantity.") from exc

    @classmethod
    def _optional_decimal(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        return cls._decimal(value, default=Decimal("0"))
