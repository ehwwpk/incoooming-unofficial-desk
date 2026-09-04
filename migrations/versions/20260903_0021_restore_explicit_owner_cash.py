"""Restore explicit owner flows and normalize Schwab cash interest."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260903_0021"
down_revision: str | None = "20260903_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OWNER_FLOW_TYPES = ("CASH_RECEIPT", "CASH_DISBURSEMENT")


def upgrade() -> None:
    quoted = ", ".join(f"'{value}'" for value in OWNER_FLOW_TYPES)
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
    op.execute(
        """
        UPDATE cash_movements
        SET movement_type = 'fee'
        WHERE movement_type = 'other'
          AND UPPER(COALESCE(description, '')) LIKE 'STOCK BORROW FEE/%'
          AND raw_event_id IN (
              SELECT id
              FROM raw_broker_events
              WHERE json_extract(payload, '$.type') = 'JOURNAL'
          )
        """
    )
    op.execute(
        """
        UPDATE cash_movements
        SET movement_type = 'trade_settlement'
        WHERE movement_type = 'other'
          AND (
              UPPER(COALESCE(description, '')) LIKE 'TRF FUNDS FRM TYPE %'
              OR UPPER(COALESCE(description, '')) LIKE 'TRF FUNDS TO TYPE %'
          )
          AND raw_event_id IN (
              SELECT id
              FROM raw_broker_events
              WHERE json_extract(payload, '$.type') = 'JOURNAL'
          )
        """
    )
    op.execute(
        """
        UPDATE cash_movements
        SET movement_type = 'interest'
        WHERE movement_type = 'dividend'
          AND UPPER(COALESCE(description, '')) LIKE 'SCHWAB1 INT %'
          AND raw_event_id IN (
              SELECT id
              FROM raw_broker_events
              WHERE json_extract(payload, '$.type') = 'DIVIDEND_OR_INTEREST'
          )
        """
    )


def downgrade() -> None:
    quoted = ", ".join(f"'{value}'" for value in OWNER_FLOW_TYPES)
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
    op.execute(
        """
        UPDATE cash_movements
        SET movement_type = 'other'
        WHERE movement_type IN ('fee', 'trade_settlement')
          AND raw_event_id IN (
              SELECT id
              FROM raw_broker_events
              WHERE json_extract(payload, '$.type') = 'JOURNAL'
          )
          AND (
              UPPER(COALESCE(description, '')) LIKE 'STOCK BORROW FEE/%'
              OR UPPER(COALESCE(description, '')) LIKE 'TRF FUNDS FRM TYPE %'
              OR UPPER(COALESCE(description, '')) LIKE 'TRF FUNDS TO TYPE %'
          )
        """
    )
    op.execute(
        """
        UPDATE cash_movements
        SET movement_type = 'dividend'
        WHERE movement_type = 'interest'
          AND UPPER(COALESCE(description, '')) LIKE 'SCHWAB1 INT %'
          AND raw_event_id IN (
              SELECT id
              FROM raw_broker_events
              WHERE json_extract(payload, '$.type') = 'DIVIDEND_OR_INTEREST'
          )
        """
    )
