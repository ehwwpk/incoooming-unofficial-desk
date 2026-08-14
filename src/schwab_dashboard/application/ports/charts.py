from typing import Protocol

from schwab_dashboard.application.charts.models import CampaignChart


class CampaignChartReader(Protocol):
    def execute(self, symbol: str) -> CampaignChart: ...
