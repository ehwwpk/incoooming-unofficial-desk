from __future__ import annotations

from datetime import date
from typing import Protocol

from schwab_dashboard.domain.opportunity import RadarMarketBundle, RadarMode


class OpportunityMarketGateway(Protocol):
    def fetch(
        self,
        *,
        symbol: str,
        mode: RadarMode,
        from_date: date,
        to_date: date,
    ) -> RadarMarketBundle: ...
