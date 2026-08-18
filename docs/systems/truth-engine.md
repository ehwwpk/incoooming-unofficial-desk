# Incoooming Truth Engine

## Job to be done

Incoooming's Truth Engine turns broker and import data into an auditable, replayable ledger. It must
answer "where did this number come from?" before any risk, attribution, or volatility feature is
allowed to present the number as fact.

This is the first dependency for every other approved system. It is not a trade journal UI and it is
not a pricing engine.

## Non-negotiable truths

- Raw source payloads are immutable, hashed, timestamped, and parser-versioned.
- Normalized records point back to the raw record that produced them.
- Executions, cash movements, lifecycle events, positions, and market observations are different
  facts. One must not be synthesized from another without a visible derivation.
- Money and quantities use decimal arithmetic. Missing values remain missing, not zero.
- Cash signs are from the account's perspective: credit positive, debit negative.
- A roll is two executions plus an optional relationship; it is never stored as one fictional trade.
- Assignment is a lifecycle outcome. It is not automatically an error or a losing trade.
- Open marked P/L is an estimate at a timestamp. It is not realized cash or realized P/L.
- Standard equity options normally represent 100 shares, but adjusted contracts may have a
  nonstandard deliverable. The schema never hard-codes 100 as universal truth.

## Canonical records

### Instrument

Stable broker-neutral identity with source key, symbol, asset class, description, underlying,
option side, strike, expiration, contract multiplier, and structured deliverable. It records first
and last observation timestamps so symbol metadata can evolve without losing identity.

### Execution

One filled buy or sell. Required economics are side, position effect, quantity, price, gross amount,
fees, and signed net cash. Order identity is optional because partial fills are independent facts.
Execution identity is idempotent within account and source.

### Cash movement

One signed account cash event, categorized as premium, dividend, fee, interest, transfer, trade
settlement, tax/withholding, or other. Broker transaction feeds sometimes expose cash and execution
views of the same activity; reconciliation may link them but must not double count them.

### Option lifecycle event

Expiration, assignment, exercise, or contract adjustment. The event can point to related option and
stock instruments, stock quantity, cash effect, and broker detail. Pairing to executions is a
separate explicit relationship in a later migration.

### Market observation

An underlying or option quote/analytics snapshot at a precise timestamp. Bid, ask, last, mark,
quote quality, mark method, Greeks, IV, volume, and open interest are observed fields with source
provenance. Calculated fields retain their method/version rather than masquerading as broker facts.

## Lifecycle state machine

```text
opening execution -> open quantity -> closing execution -> closed
                                |-> expiration          -> expired
                                |-> assignment          -> assigned + share/cash effects
                                |-> exercise            -> exercised + share/cash effects
                                |-> adjustment          -> adjusted instrument/deliverable
```

The state is derived from atomic records. It is not an editable status column. Unmatched quantity
remains an explicit break rather than being guessed into a plausible state.

## Reconciliation layers

1. Structural: unique account/instrument identities, required shapes, valid decimal and timestamps.
2. Transaction: execution quantity, cash event, fee, and lifecycle linkage completeness.
3. Position: replayed quantity versus broker position snapshot at comparable timestamps.
4. Cash: replayed signed movements versus broker balances when available.
5. Market: quote freshness, crossed/one-sided markets, missing Greeks, and source gaps.

Every break has a stable code, severity, relevant identifiers, measured difference, and human
explanation. Structural errors block normalization; timing-dependent value differences may warn.

## Source drill-through contract

Every aggregate must be able to expose this chain:

```text
displayed value -> calculation result -> normalized record ids -> raw source event -> source payload
```

The first implementation stores the normalized ledger and market spine. Calculation-result
lineage and campaign relationships are separate bounded additions after the atomic records exist.

## Data quality statuses

- `observed`: supplied directly by a source.
- `derived`: deterministic calculation from observed records.
- `estimated`: model, heuristic, or proxy.
- `simulated`: scenario output, not a prediction.
- `stale`: outside the feature-specific freshness threshold.
- `unresolved`: blocked by a reconciliation break.

These statuses are metadata, not colors. UI color may reinforce them but never replace the label.

## Release slices

1. Instruments, executions, cash movements, lifecycle events, and market observations.
2. Broker/CSV normalizers with raw-event preservation and idempotency.
3. Execution pairing, campaign links, position/cash replay, and reconciliation queue.
4. Calculation lineage and source drill-through API.
5. Operator correction annotations that never mutate the source record.

## Verification requirements

- Migration upgrade from the existing Phase 1 schema and full downgrade in an isolated database.
- Round-trip exact decimals, nulls, UTC timestamps, and nonstandard option deliverables.
- Duplicate source identities are idempotent or fail explicitly; they never double count.
- Roll tests prove two execution cash effects remain separate.
- Assignment and expiration tests prove lifecycle quantity resolves without invented fills.
- Live and demo books already share the same dashboard snapshot contract; remaining work is lineage depth, not a second source of truth.

## Primary references

- OCC equity-option product specifications: <https://www.theocc.com/clearance-and-settlement/clearing/equity-options-product-specifications>
- OIC option lifecycle: <https://www.optionseducation.org/news/understanding-the-life-cycle-of-an-option-trade>
- OIC assignment guidance: <https://www.optionseducation.org/referencelibrary/faq/options-assignment>
