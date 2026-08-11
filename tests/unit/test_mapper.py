from decimal import Decimal

import pytest

from schwab_dashboard.application.errors import BrokerPayloadError
from schwab_dashboard.infrastructure.schwab.mapper import SchwabAccountMapper


def test_maps_account_hash_mask_and_decimal_positions() -> None:
    records = SchwabAccountMapper().map_records(
        [{"accountNumber": "12345678", "hashValue": "hash-abc"}],
        [
            {
                "securitiesAccount": {
                    "accountNumber": "12345678",
                    "type": "MARGIN",
                    "positions": [
                        {
                            "longQuantity": 100,
                            "shortQuantity": 0,
                            "averagePrice": 12.34,
                            "marketValue": 1400,
                            "instrument": {
                                "symbol": "XYZ",
                                "cusip": "cusip-xyz",
                                "assetType": "EQUITY",
                            },
                        }
                    ],
                }
            }
        ],
    )

    assert len(records) == 1
    assert records[0].account.external_key == "hash-abc"
    assert records[0].account.account_mask == "...5678"
    assert records[0].positions[0].long_quantity == Decimal("100")
    assert records[0].positions[0].average_price == Decimal("12.34")


def test_refuses_account_without_hash_match() -> None:
    with pytest.raises(BrokerPayloadError, match="account hash"):
        SchwabAccountMapper().map_records(
            [{"accountNumber": "1111", "hashValue": "hash-one"}],
            [{"securitiesAccount": {"accountNumber": "2222", "positions": []}}],
        )


def test_maps_balances_and_short_call_identity() -> None:
    records = SchwabAccountMapper().map_records(
        [{"accountNumber": "12345678", "hashValue": "hash-abc"}],
        [
            {
                "securitiesAccount": {
                    "accountNumber": "12345678",
                    "type": "MARGIN",
                    "isPortfolioMargin": True,
                    "currentBalances": {
                        "liquidationValue": 125000,
                        "equity": 124500,
                        "marginBalance": -25000,
                        "buyingPower": 50000,
                    },
                    "positions": [
                        {
                            "longQuantity": 0,
                            "shortQuantity": 2,
                            "averageShortPrice": 2.45,
                            "marketValue": -330,
                            "shortOpenProfitLoss": 160,
                            "instrument": {
                                "symbol": "KTOS  260918C00075000",
                                "description": "KTOS SEP 18 2026 75 Call",
                                "assetType": "OPTION",
                                "putCall": "CALL",
                                "underlyingSymbol": "KTOS",
                            },
                        }
                    ],
                }
            }
        ],
    )

    assert records[0].balances is not None
    assert records[0].balances.liquidation_value == Decimal("125000")
    assert records[0].balances.is_portfolio_margin is True
    position = records[0].positions[0]
    assert position.average_price == Decimal("2.45")
    assert position.underlying_symbol == "KTOS"
    assert position.option_type == "CALL"
    assert position.expiration_date.isoformat() == "2026-09-18"
    assert position.strike == Decimal("75")
    assert position.short_open_profit_loss == Decimal("160")
