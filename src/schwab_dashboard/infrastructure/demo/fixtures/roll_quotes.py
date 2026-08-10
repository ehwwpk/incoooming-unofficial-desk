from __future__ import annotations

from datetime import date
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import RollQuoteCandidate

D = Decimal

ROLL_QUOTE_CANDIDATES = {
    ("KTOS", date(2026, 9, 18), D("65")): (
        RollQuoteCandidate(
            expires_on=date(2026, 10, 9),
            strike=D("70"),
            sell_bid_per_share=D("3.40"),
            quote_source="SIMULATED BID",
        ),
        RollQuoteCandidate(
            expires_on=date(2026, 10, 30),
            strike=D("75"),
            sell_bid_per_share=D("3.35"),
            quote_source="SIMULATED BID",
        ),
    ),
}
