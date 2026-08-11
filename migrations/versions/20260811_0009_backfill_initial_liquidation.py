"""Backfill start-of-day values already preserved in immutable broker payloads."""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0009"
down_revision: str | None = "20260811_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    balances = sa.table(
        "account_balance_snapshots",
        sa.column("id", sa.String),
        sa.column("raw_event_id", sa.String),
        sa.column("initial_liquidation_value", sa.Numeric(28, 10)),
    )
    raw_events = sa.table(
        "raw_broker_events",
        sa.column("id", sa.String),
        sa.column("payload", sa.JSON),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(balances.c.id, raw_events.c.payload).join(
            raw_events,
            raw_events.c.id == balances.c.raw_event_id,
        )
    ).mappings()
    for row in rows:
        value = _initial_liquidation_value(row["payload"])
        if value is None:
            continue
        connection.execute(
            balances.update()
            .where(balances.c.id == row["id"])
            .values(initial_liquidation_value=value)
        )


def downgrade() -> None:
    # The column belongs to the preceding schema migration. Retaining a
    # truthful backfill is safer than erasing it during a code-only downgrade.
    pass


def _initial_liquidation_value(payload: Any) -> Decimal | None:
    if not isinstance(payload, Mapping):
        return None
    account = payload.get("securitiesAccount", payload)
    if not isinstance(account, Mapping):
        return None
    initial = account.get("initialBalances")
    if not isinstance(initial, Mapping):
        return None
    value = initial.get("liquidationValue")
    return Decimal(str(value)) if value is not None else None
