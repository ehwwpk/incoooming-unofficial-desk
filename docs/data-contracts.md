# Phase 1 data contracts

## Raw broker event

The raw event is the audit source. It records the source system, sync run, event type, observed timestamp, parser version, item key, payload hash, and untouched JSON payload.

Idempotency is scoped to `(sync_run_id, item_key)`. A second real sync is a new observation even when the payload is unchanged.

## Account identity

`external_account_key` is Schwab's account hash. The visible account number is never the durable key and is persisted only as a mask such as `...1234`.

## Position snapshot

A position snapshot is not a trade ledger. It records what Schwab reported at one observation time:

- account identity
- instrument key and symbol
- asset type
- long and short quantities
- average price and market value when supplied
- day P/L fields when supplied
- pointer to the raw event

Future transaction replay must reconcile to these snapshots; snapshots do not create synthetic transactions by themselves.

## Reconciliation issue

An issue has a stable code, severity, human-readable message, optional instrument key, and structured context. Structural errors block a run. Market-value differences can be warnings when timestamps differ.

## Time and numeric rules

- Persist timestamps in UTC with explicit timezone information at application boundaries.
- Interpret trading-calendar groupings in America/New_York in the analytics layer. Persisted
  naive broker timestamps are normalized UTC values; plain dates remain calendar dates.
- Parse quantity and money values through `Decimal(str(value))`.
- Preserve `null` when the broker omitted a value; do not silently substitute zero.
