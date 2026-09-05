from datetime import UTC, date, datetime
from itertools import pairwise

import pytest

from schwab_dashboard.domain.opportunity import RadarMode
from schwab_dashboard.infrastructure.demo.opportunity import DemoOpportunityMarketGateway


@pytest.mark.parametrize("symbol", ("CVX", "KTOS", "URNM"))
@pytest.mark.parametrize("mode", tuple(RadarMode))
def test_demo_strikes_do_not_offer_inverted_call_or_put_spreads(symbol, mode) -> None:
    gateway = DemoOpportunityMarketGateway(clock=lambda: datetime(2026, 8, 7, 21, 15, tzinfo=UTC))
    bundle = gateway.fetch(
        symbol=symbol,
        mode=mode,
        from_date=date(2026, 8, 7),
        to_date=date(2026, 10, 30),
    )
    for expiry in {contract.expiration_date for contract in bundle.contracts}:
        rows = sorted(
            (contract for contract in bundle.contracts if contract.expiration_date == expiry),
            key=lambda contract: contract.strike,
        )
        for contract in rows:
            assert 0 <= contract.bid <= contract.mark <= contract.ask
        for lower, higher in pairwise(rows):
            if mode is RadarMode.COVERED_CALL:
                assert lower.bid >= higher.bid, (expiry, lower.strike, higher.strike)
                assert lower.ask >= higher.ask, (expiry, lower.strike, higher.strike)
            else:
                assert lower.bid <= higher.bid, (expiry, lower.strike, higher.strike)
                assert lower.ask <= higher.ask, (expiry, lower.strike, higher.strike)
