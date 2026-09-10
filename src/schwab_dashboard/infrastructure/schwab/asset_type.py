from collections.abc import Mapping
from typing import Any


def normalized_asset_type(instrument: Mapping[str, Any]) -> str:
    """Preserve the broker class, except for explicitly identified ETF shares.

    The trader API reports ETFs as COLLECTIVE_INVESTMENT with a separate type;
    its quote API uses EQUITY/ETF instead. A ticker or description is not proof.
    """

    asset_type = str(instrument.get("assetType") or "UNKNOWN").strip().upper()
    subtype = str(instrument.get("type") or "").strip().upper()
    if asset_type == "COLLECTIVE_INVESTMENT" and subtype == "EXCHANGE_TRADED_FUND":
        return "ETF"
    return asset_type
