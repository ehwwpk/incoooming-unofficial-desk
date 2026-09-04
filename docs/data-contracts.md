# Incoooming data contracts

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

Transaction replay must reconcile to these snapshots; snapshots do not create synthetic
transactions by themselves.

## Transactions and lifecycle events

Executions retain asset type, quantity, price, gross cash, net cash, fees, position effect, and
contract metadata when the source supplies them. Cash movements keep dividends, interest,
financing, fees, withholding, owner transfers, and unknown activity separate. Lifecycle records
keep assignment, exercise, expiration, and adjustment events separate from executions.

Assignments and exercises may be matched to broker stock-delivery executions. Matching uses stable
source fields and duplicate occurrence numbers; it never uses process memory addresses. Ambiguous
matches remain unresolved and are excluded from affected comparison paths.

## Reconciliation issue

An issue has a stable code, severity, human-readable message, optional instrument key, and structured context. Structural errors block a run. Market-value differences can be warnings when timestamps differ.

## Time and numeric rules

- Persist timestamps in UTC with explicit timezone information at application boundaries.
- Interpret trading-calendar groupings in America/New_York in the analytics layer. Persisted
  naive broker timestamps are normalized UTC values; plain dates remain calendar dates.
- Parse quantity and money values through `Decimal(str(value))`.
- Preserve `null` when the broker omitted a value; do not silently substitute zero.
