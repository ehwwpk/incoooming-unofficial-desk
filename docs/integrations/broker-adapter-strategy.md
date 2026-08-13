# Broker adapter strategy

## Product rule

The dashboard owns a canonical, append-oriented truth ledger. Broker APIs, aggregators, and uploaded files are evidence sources—not the analytics model and not unquestioned truth.

The public integration shape is deliberately layered:

1. Direct broker adapters where an approved, supportable API exposes the required data.
2. A read-only aggregator adapter for broad brokerage coverage and hosted user authorization.
3. CSV or statement imports as a durable fallback and history backfill path.

All three paths normalize into the same instruments, executions, cash movements, lifecycle events, market observations, and source metadata.

## Capability negotiation

Each adapter declares support independently for accounts, balances, positions, activities, executions, option contract metadata, tax lots, open orders, and market quotes. Each capability also declares a refresh class and one of:

- `available`: implemented and verified for this adapter;
- `conditional`: provider, brokerage, plan, authorization, or payload verification is still required;
- `unavailable`: the source does not supply the fact;
- `unknown`: the adapter has made no defensible claim.

The UI and calculation engines must degrade by capability. They must never infer that “connected” means every analytical input is present.

## Adapter acceptance checks

No source is promoted to trusted live use until fixtures and reconciliation tests verify:

- long/short signs and position netting;
- option quantity units and contract multipliers;
- corporate-action and assignment semantics;
- execution, fee, dividend, and cash movement identifiers;
- timestamp timezone and trading-date boundaries;
- activity history horizon and refresh cadence;
- duplicate delivery and idempotent replay;
- quote quality, mark method, and observation time;
- raw-source retention and normalized-record provenance.

## Current status

- Schwab direct: OAuth, balances, positions, transaction history, option marks and Greeks, option
  chains around open contracts, and daily underlying history are running against verified real
  payloads. Reconciliation and source-time visibility remain mandatory.
- Multi-broker aggregator: capability contract exists. SnapTrade Personal is the preferred next
  proof of concept for the owner's Robinhood account; it is not integrated yet.
- CSV/statement import: isolated multi-file books, auditable raw rows, alias-based positions and
  activity normalization, source switching, and generic templates are implemented. Exact
  broker-specific export variants still require sanitized fixtures before claiming full parity.
- Trading: intentionally outside the adapter interface. The analytics product is read-only.

Premium Radar requires a separate capability for candidate option chains over configured DTE and
strike windows. A provider that can read open option positions but cannot supply timely chain,
quote, IV, and Greek observations can populate the ledger but cannot power the complete Radar.

## Fidelity and Robinhood implication

Fidelity emphasizes authorized third-party data sharing rather than credential sharing. Robinhood limits unsanctioned API control and points users toward supported third-party connections. Therefore, broad public coverage is more realistically achieved with an approved aggregator plus file import, while retaining direct adapters where official access is supportable.
