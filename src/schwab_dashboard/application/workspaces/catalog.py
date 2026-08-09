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
        label="Open Book",
        short_label="BOOK",
        eyebrow="LIVE OBLIGATIONS",
        description="Every open call, its remaining liability, strike distance, and time decay.",
        route="/workspaces/risk",
        template_name="workspaces/_open_book.html",
        window_name="iud-open-book",
        function_key="F2",
    ),
    WorkspaceDefinition(
        key=WorkspaceKey.ATTRIBUTION,
        label="Strategy Review",
        short_label="REVIEW",
        eyebrow="RESULTS EXPLAINED",
        description="Cash results, pace, outcomes, and capital recovery without mark-to-cash blur.",
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
        label="Source Ledger",
        short_label="LEDGER",
        eyebrow="PROVENANCE / RECORDS",
        description=(
            "Positions, normalized call activity, and exactly which source supplied each fact."
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
