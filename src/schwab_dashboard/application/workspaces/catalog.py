from __future__ import annotations

from dataclasses import dataclass

from schwab_dashboard.domain.workspace import WorkspaceKey


@dataclass(frozen=True, slots=True)
class WorkspaceDefinition:
    """Stable workspace identity paired with replaceable interface copy."""

    key: WorkspaceKey
    label: str
    short_label: str
    eyebrow: str
    description: str
    route: str
    template_name: str
    window_name: str
    function_key: str


WORKSPACE_CATALOG = (
    WorkspaceDefinition(
        key=WorkspaceKey.DESK,
        label="Desk",
        short_label="DESK",
        eyebrow="INCOME COMMAND",
        description="Portfolio pulse, premium cash, and the names that need attention.",
        route="/",
        template_name="dashboard.html",
        window_name="iud-desk",
        function_key="F1",
    ),
    WorkspaceDefinition(
        key=WorkspaceKey.RISK,
        label="Open Calls",
        short_label="CALLS",
        eyebrow="LIVE OBLIGATIONS",
        description="Cross-portfolio obligations, strike pressure, marks, and time decay.",
        route="/workspaces/risk",
        template_name="workspaces/_open_book.html",
        window_name="iud-open-book",
        function_key="F2",
    ),
    WorkspaceDefinition(
        key=WorkspaceKey.ATTRIBUTION,
        label="Results",
        short_label="RESULTS",
        eyebrow="RESULTS EXPLAINED",
        description=(
            "Monthly cash, campaign economics, and strategy results without mark-to-cash blur."
        ),
        route="/workspaces/attribution",
        template_name="workspaces/_strategy_review.html",
        window_name="iud-strategy-review",
        function_key="F3",
    ),
    WorkspaceDefinition(
        key=WorkspaceKey.VOLATILITY,
        label="Volatility Lab",
        short_label="VOL",
        eyebrow="PRICE / VOL REGIME",
        description="Realized movement, current option IV context, and data-quality boundaries.",
        route="/workspaces/volatility",
        template_name="workspaces/_volatility_lab.html",
        window_name="iud-volatility-lab",
        function_key="F4",
    ),
    WorkspaceDefinition(
        key=WorkspaceKey.RECORDS,
        label="Data Health",
        short_label="DATA",
        eyebrow="SOURCES / COVERAGE",
        description=(
            "Broker feeds, coverage gaps, provenance, and source readiness in one maintenance view."
        ),
        route="/workspaces/records",
        template_name="workspaces/_source_ledger.html",
        window_name="iud-source-ledger",
        function_key="F5",
    ),
)


def list_workspaces() -> tuple[WorkspaceDefinition, ...]:
    return WORKSPACE_CATALOG


def get_workspace(key: WorkspaceKey) -> WorkspaceDefinition:
    return next(item for item in WORKSPACE_CATALOG if item.key is key)
