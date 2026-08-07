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
