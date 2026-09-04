"""Stop treating ambiguous broker journals as owner capital."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260903_0019"
down_revision: str | None = "20260903_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AMBIGUOUS_TYPES = ("JOURNAL",)


def upgrade() -> None:
    quoted = ", ".join(f"'{value}'" for value in AMBIGUOUS_TYPES)
    op.execute(
        f"""
        UPDATE cash_movements
        SET movement_type = 'other'
        WHERE movement_type = 'transfer'
          AND raw_event_id IN (
              SELECT id
              FROM raw_broker_events
              WHERE json_extract(payload, '$.type') IN ({quoted})
          )
        """
    )


def downgrade() -> None:
    quoted = ", ".join(f"'{value}'" for value in AMBIGUOUS_TYPES)
    op.execute(
        f"""
        UPDATE cash_movements
        SET movement_type = 'transfer'
        WHERE movement_type = 'other'
          AND raw_event_id IN (
              SELECT id
              FROM raw_broker_events
              WHERE json_extract(payload, '$.type') IN ({quoted})
          )
        """
    )
