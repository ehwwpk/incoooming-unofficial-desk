from __future__ import annotations

from schwab_dashboard.application.ports.brokerage_data import (
    BrokerageSourceProfile,
    BrokerCapability,
    CapabilityState,
    CapabilitySupport,
    DataSourceKind,
    RefreshClass,
)


def planned_source_profiles() -> tuple[BrokerageSourceProfile, ...]:
    """Honest integration paths, not claims of finished adapters."""

    return (
        BrokerageSourceProfile(
            source_key="schwab-direct",
            display_name="Schwab direct",
            kind=DataSourceKind.DIRECT_BROKER,
            read_only=True,
            support=(
                _support(BrokerCapability.ACCOUNTS, CapabilityState.AVAILABLE, "Sync shell built"),
                _support(BrokerCapability.POSITIONS, CapabilityState.AVAILABLE, "Sync shell built"),
                _support(
                    BrokerCapability.ACTIVITIES,
                    CapabilityState.CONDITIONAL,
                    "Mapping waits for approved documentation and verified payload fixtures",
                ),
                _support(
                    BrokerCapability.MARKET_QUOTES,
                    CapabilityState.CONDITIONAL,
                    "Market-data authorization and payload verification required",
                ),
            ),
        ),
        BrokerageSourceProfile(
            source_key="aggregator",
            display_name="Multi-broker aggregator",
            kind=DataSourceKind.AGGREGATOR,
            read_only=True,
            support=(
                _support(
                    BrokerCapability.ACCOUNTS,
                    CapabilityState.CONDITIONAL,
                    "Provider and brokerage support vary",
                ),
                _support(
                    BrokerCapability.POSITIONS,
                    CapabilityState.CONDITIONAL,
                    "Verify quantities and option multipliers per provider",
                ),
                _support(
                    BrokerCapability.ACTIVITIES,
                    CapabilityState.CONDITIONAL,
                    "History depth and refresh cadence vary by brokerage",
                ),
            ),
        ),
        BrokerageSourceProfile(
            source_key="statement-import",
            display_name="CSV / statement import",
            kind=DataSourceKind.FILE_IMPORT,
            read_only=True,
            support=(
                _support(
                    BrokerCapability.POSITIONS,
                    CapabilityState.CONDITIONAL,
                    "Broker-specific importer required",
                    RefreshClass.FILE_SNAPSHOT,
                ),
                _support(
                    BrokerCapability.ACTIVITIES,
                    CapabilityState.CONDITIONAL,
                    "Broker-specific importer required",
                    RefreshClass.FILE_SNAPSHOT,
                ),
                _support(
                    BrokerCapability.EXECUTIONS,
                    CapabilityState.CONDITIONAL,
                    "Preserve original file and row provenance",
                    RefreshClass.FILE_SNAPSHOT,
                ),
            ),
        ),
    )


def _support(
    capability: BrokerCapability,
    state: CapabilityState,
    note: str,
    refresh: RefreshClass = RefreshClass.UNKNOWN,
) -> CapabilitySupport:
    return CapabilitySupport(
        capability=capability,
        state=state,
        refresh=refresh,
        note=note,
    )
