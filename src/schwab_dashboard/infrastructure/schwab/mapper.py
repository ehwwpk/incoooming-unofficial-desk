from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from schwab_dashboard.application.errors import BrokerPayloadError
from schwab_dashboard.application.ports.broker import BrokerAccountRecord
from schwab_dashboard.domain.broker import (
    BrokerAccount,
    BrokerAccountBalances,
    BrokerPosition,
)
from schwab_dashboard.infrastructure.schwab.option_symbol import parse_occ_option_symbol


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
                    balances=self._map_balances(securities_account),
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
        parsed_option = parse_occ_option_symbol(symbol) if asset_type.upper() == "OPTION" else None
        long_quantity = self._decimal(payload.get("longQuantity"), default=Decimal("0"))
        short_quantity = self._decimal(payload.get("shortQuantity"), default=Decimal("0"))
        average_price_value = (
            payload.get("averageShortPrice")
            if short_quantity > 0
            else payload.get("averageLongPrice")
        )
        if average_price_value is None:
            average_price_value = payload.get("averagePrice")

        return BrokerPosition(
            instrument_key=instrument_key,
            symbol=symbol,
            asset_type=asset_type,
            long_quantity=long_quantity,
            short_quantity=short_quantity,
            average_price=self._optional_decimal(average_price_value),
            market_value=self._optional_decimal(payload.get("marketValue")),
            day_profit_loss=self._optional_decimal(payload.get("currentDayProfitLoss")),
            day_profit_loss_percent=self._optional_decimal(
                payload.get("currentDayProfitLossPercentage")
            ),
            description=str(instrument.get("description") or "").strip(),
            underlying_symbol=(
                str(instrument.get("underlyingSymbol") or "").strip()
                or (parsed_option.underlying_symbol if parsed_option else None)
            ),
            option_type=(
                str(instrument.get("putCall") or "").strip().upper()
                or (parsed_option.option_type if parsed_option else None)
            ),
            expiration_date=parsed_option.expiration_date if parsed_option else None,
            strike=parsed_option.strike if parsed_option else None,
            long_open_profit_loss=self._optional_decimal(payload.get("longOpenProfitLoss")),
            short_open_profit_loss=self._optional_decimal(payload.get("shortOpenProfitLoss")),
        )

    def _map_balances(self, account: Mapping[str, Any]) -> BrokerAccountBalances:
        current = account.get("currentBalances") or {}
        if not isinstance(current, Mapping):
            raise BrokerPayloadError("Schwab currentBalances payload is not an object.")
        return BrokerAccountBalances(
            liquidation_value=self._optional_decimal(current.get("liquidationValue")),
            equity=self._optional_decimal(current.get("equity")),
            cash_balance=self._optional_decimal(current.get("cashBalance")),
            money_market_fund=self._optional_decimal(current.get("moneyMarketFund")),
            margin_balance=self._optional_decimal(current.get("marginBalance")),
            buying_power=self._optional_decimal(current.get("buyingPower")),
            available_funds=self._optional_decimal(current.get("availableFunds")),
            maintenance_requirement=self._optional_decimal(current.get("maintenanceRequirement")),
            long_market_value=self._optional_decimal(current.get("longMarketValue")),
            short_market_value=self._optional_decimal(current.get("shortMarketValue")),
            long_option_market_value=self._optional_decimal(current.get("longOptionMarketValue")),
            short_option_market_value=self._optional_decimal(current.get("shortOptionMarketValue")),
            is_portfolio_margin=bool(account.get("isPortfolioMargin")),
            is_intraday_margin=bool(account.get("isIntradayMargin")),
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
