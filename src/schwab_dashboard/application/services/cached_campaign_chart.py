from __future__ import annotations

from collections.abc import Callable, Hashable

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
        cache_partition: Callable[[], Hashable] | None = None,
    ) -> None:
        self._delegate = delegate
        self._cache = cache
        self._key_prefix = key_prefix
        self._cache_partition = cache_partition

    def execute(self, symbol: str) -> CampaignChart:
        normalized = symbol.strip().upper()
        partition = self._cache_partition() if self._cache_partition is not None else None
        return self._cache.get_or_load(
            (self._key_prefix, normalized, partition),
            lambda: self._delegate.execute(normalized),
        )
