"""Recover ETF classifications and delivery links from original Schwab evidence."""

import json
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "20260910_0022"
down_revision: str | None = "20260903_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    # Match each historical position to its own immutable raw observation.
    # Never classify a fund from its ticker, description, or another account.
    connection.execute(
        sa.text("""
        UPDATE position_snapshots AS p SET asset_type = 'ETF'
        WHERE UPPER(TRIM(p.asset_type)) = 'COLLECTIVE_INVESTMENT'
          AND EXISTS (SELECT 1 FROM accounts a WHERE a.id = p.account_id
                      AND a.source = 'schwab')
          AND EXISTS (
            SELECT 1 FROM raw_broker_events r,
              json_each(r.payload, '$.securitiesAccount.positions') AS item
            WHERE r.id = p.raw_event_id
              AND json_extract(item.value, '$.instrument.symbol') = p.symbol
              AND TRIM(COALESCE(NULLIF(json_extract(item.value, '$.instrument.cusip'), ''),
                               json_extract(item.value, '$.instrument.symbol'))) = p.instrument_key
              AND UPPER(TRIM(json_extract(item.value, '$.instrument.assetType')))
                    = 'COLLECTIVE_INVESTMENT'
              AND UPPER(TRIM(json_extract(item.value, '$.instrument.type')))
                    = 'EXCHANGE_TRADED_FUND'
          )
    """)
    )

    # Executions reference the instrument table. Repair the exact security ID
    # found in that execution/cash/lifecycle record, not every row with its ticker.
    rows = (
        connection.execute(
            sa.text("""
        SELECT DISTINCT i.id, i.external_key, i.symbol, r.payload
        FROM instruments i
        JOIN (
          SELECT instrument_id, raw_event_id FROM executions WHERE source = 'schwab'
          UNION SELECT instrument_id, raw_event_id FROM cash_movements WHERE source = 'schwab'
          UNION SELECT stock_instrument_id, raw_event_id FROM option_lifecycle_events
                WHERE source = 'schwab'
          UNION SELECT option_instrument_id, raw_event_id FROM option_lifecycle_events
                WHERE source = 'schwab'
        ) refs ON refs.instrument_id = i.id
        JOIN raw_broker_events r ON r.id = refs.raw_event_id
        WHERE i.source = 'schwab' AND i.asset_type IN ('mutual_fund', 'unknown')
    """)
        )
        .mappings()
        .all()
    )
    for row in rows:
        if any(
            _is_etf(item.get("instrument"))
            and _key(item["instrument"]) == row["external_key"]
            and item["instrument"].get("symbol") == row["symbol"]
            for item in _items(json.loads(row["payload"]))
        ):
            connection.execute(
                sa.text("UPDATE instruments SET asset_type = 'etf' WHERE id = :id"),
                {"id": row["id"]},
            )

    # Older parsers missed ETF shares in assignment/exercise deliveries. Restore
    # only a single explicit ETF leg paired with a single matching option leg.
    rows = (
        connection.execute(
            sa.text("""
        SELECT l.*, i.external_key AS option_key, r.payload
        FROM option_lifecycle_events l
        JOIN instruments i ON i.id = l.option_instrument_id
        JOIN raw_broker_events r ON r.id = l.raw_event_id
        WHERE l.source = 'schwab'
    """)
        )
        .mappings()
        .all()
    )
    for row in rows:
        payload = json.loads(row["payload"])
        items = _items(payload)
        stocks = [
            item
            for item in items
            if _is_etf(item.get("instrument")) or _type(item.get("instrument")) in {"EQUITY", "ETF"}
        ]
        options = [
            item
            for item in items
            if _type(item.get("instrument")) == "OPTION"
            and Decimal(str(item.get("amount") or 0)) != 0
        ]
        if (
            payload.get("type") != "RECEIVE_AND_DELIVER"
            or len(stocks) != 1
            or len(options) != 1
            or not _is_etf(stocks[0].get("instrument"))
            or _key(options[0]["instrument"]) != row["option_key"]
        ):
            continue
        stock_id = connection.execute(
            sa.text("""
            SELECT id FROM instruments WHERE source = 'schwab'
              AND external_key = :key AND symbol = :symbol
        """),
            {"key": _key(stocks[0]["instrument"]), "symbol": stocks[0]["instrument"].get("symbol")},
        ).scalar_one_or_none()
        if stock_id is None:
            continue
        stock_quantity = abs(Decimal(str(stocks[0].get("amount") or 0))) or None
        cash_amount = Decimal(str(payload.get("netAmount") or 0)) or None
        expected_details = {
            "source_type": "RECEIVE_AND_DELIVER",
            "position_effect": str(options[0].get("positionEffect") or "UNKNOWN"),
            "description": str(payload.get("description") or ""),
        }
        details = json.loads(row["details"])
        details.pop("delivery_ambiguous", None)
        if details != expected_details:
            continue
        expected = {
            "stock_instrument_id": stock_id,
            "stock_quantity": stock_quantity,
            "cash_amount": cash_amount,
        }
        if any(row[key] is not None and row[key] != value for key, value in expected.items()):
            continue
        # Binding decimal strings avoids binary floating-point rounding.
        connection.execute(
            sa.text("""
            UPDATE option_lifecycle_events SET stock_instrument_id = :stock_instrument_id,
              stock_quantity = :stock_quantity, cash_amount = :cash_amount, details = :details
            WHERE id = :id
        """),
            {
                "id": row["id"],
                "stock_instrument_id": stock_id,
                "stock_quantity": str(stock_quantity) if stock_quantity is not None else None,
                "cash_amount": str(cash_amount) if cash_amount is not None else None,
                "details": json.dumps(expected_details),
            },
        )
        connection.execute(
            sa.text("UPDATE instruments SET asset_type = 'etf' WHERE id = :id"),
            {"id": stock_id},
        )


def downgrade() -> None:
    # This only corrects derived classifications using retained broker evidence.
    # A schema downgrade must not erase known ETF shares or delivery facts.
    pass


def _type(instrument: Any) -> str:
    return (
        str(instrument.get("assetType") or "").strip().upper()
        if isinstance(instrument, Mapping)
        else ""
    )


def _is_etf(instrument: Any) -> bool:
    return (
        _type(instrument) == "COLLECTIVE_INVESTMENT"
        and str(instrument.get("type") or "").strip().upper() == "EXCHANGE_TRADED_FUND"
    )


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [item for item in payload.get("transferItems", []) if isinstance(item, Mapping)]


def _key(instrument: Mapping[str, Any]) -> str:
    for field in ("instrumentId", "cusip", "uniformSymbol", "symbol"):
        if instrument.get(field) is not None and str(instrument[field]).strip():
            return str(instrument[field]).strip()
    return ""
