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

- Schwab direct: OAuth and account/position sync shell exist; full activity and market mapping waits for approved documentation and verified real payloads.
- Multi-broker aggregator: capability contract exists; no vendor is selected or integrated.
- CSV/statement import: capability contract exists; broker-specific parsers are not implemented.
- Trading: intentionally outside the adapter interface. The analytics product is read-only.

## Fidelity and Robinhood implication

Fidelity emphasizes authorized third-party data sharing rather than credential sharing. Robinhood limits unsanctioned API control and points users toward supported third-party connections. Therefore, broad public coverage is more realistically achieved with an approved aggregator plus file import, while retaining direct adapters where official access is supportable.
