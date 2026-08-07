from typing import Protocol

from schwab_dashboard.application.dashboard.models import DashboardSnapshot


class DashboardReader(Protocol):
    def execute(self) -> DashboardSnapshot: ...
