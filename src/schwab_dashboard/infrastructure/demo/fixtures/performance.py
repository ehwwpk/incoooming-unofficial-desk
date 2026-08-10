"""Stable public facade for the demo performance fixture modules."""

from schwab_dashboard.infrastructure.demo.fixtures.performance_attribution import (
    build_strategy_attribution,
)
from schwab_dashboard.infrastructure.demo.fixtures.performance_charts import (
    build_cash_chart_series,
)
from schwab_dashboard.infrastructure.demo.fixtures.performance_ledger import (
    build_monthly_performance,
    build_quarter_history,
)
from schwab_dashboard.infrastructure.demo.fixtures.performance_objectives import (
    build_basis_lens,
    build_objective_summary,
)
from schwab_dashboard.infrastructure.demo.fixtures.performance_windows import (
    build_performance_windows,
)

__all__ = [
    "build_basis_lens",
    "build_cash_chart_series",
    "build_monthly_performance",
    "build_objective_summary",
    "build_performance_windows",
    "build_quarter_history",
    "build_strategy_attribution",
]
