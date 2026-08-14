from __future__ import annotations

from collections.abc import Hashable

from schwab_dashboard.application.charts.models import CampaignChart
from schwab_dashboard.application.ports.charts import CampaignChartReader
from schwab_dashboard.application.services.runtime_cache import GenerationCache


class CachedCampaignChartReader:
    def __init__(
        self,
        *,
        delegate: CampaignChartReader,
        cache: GenerationCache,
        key_prefix: Hashable,
    ) -> None:
        self._delegate = delegate
        self._cache = cache
        self._key_prefix = key_prefix

    def execute(self, symbol: str) -> CampaignChart:
        normalized = symbol.strip().upper()
        return self._cache.get_or_load(
            (self._key_prefix, normalized),
            lambda: self._delegate.execute(normalized),
        )
