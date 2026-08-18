# Incoooming integrated platform plan

## Architectural decision

Incoooming keeps Truth Engine, Open Risk, Attribution Lab, Volatility calculations, and the Workspace System
as modules inside one local-first modular monolith. Premium Radar and the Nibwick Roll Board sit on
that same spine as Radar and Open Options projections. They share identifiers, immutable raw events,
normalized ledger records, point-in-time market observations, and calculation metadata. They do not
share UI-specific models or reach into one another's tables directly.

## Dependency order

```text
source adapters (Schwab / CSV / future aggregator)
                         |
                immutable raw events
                         |
        Truth Engine normalized atomic records
          |                    |                 |
 executions/cash/lifecycle  positions       market observations
          |                    |                 |
          +---------- projections/read models --+
                         |
        +----------------+----------------+
        |                |                |
   Open Risk       Attribution Lab    Volatility Lab
        +----------------+----------------+
                         |
                 Workspace System
```

The Workspace System may store user preferences immediately, but analytical screens cannot bypass
the underlying read models. The Open Risk Board can ship before full Attribution/Volatility
research because it consumes the same ledger and latest-snapshot spine.

## Bounded modules

### `domain`

Broker-neutral values and invariants: instruments, ledger activity, market observations, lifecycle
relationships, calculations, and reconciliation concepts. No HTTP, SQLAlchemy, FastAPI, or HTML.

### `application/ports`

Repository, broker/import, market-data, clock/calendar, and pricing contracts. Protocols are split by
capability so the unit of work does not become a god interface.

### `application/services`

Atomic use cases: ingest ledger activity, record observations, reconcile a run, build an open-book
projection, calculate attribution, normalize volatility, and save workspace preferences.

### `infrastructure`

Schwab/CSV adapters, database tables/repositories, external calendars/rates, and deterministic
pricing implementations. Source-specific shapes end at the adapter boundary.

### `api` and `web`

Versioned read endpoints and thin presentation. Templates/JavaScript format and interact with typed
responses; they do not calculate accounting, risk, or research results.

## Shared calculation envelope

Every material analytical result will eventually include:

- value and unit;
- as-of timestamp and timezone;
- observed/derived/estimated/simulated status;
- method name and version;
- input/source record ids;
- data quality and freshness;
- user-selected filters and denominator where applicable.

This envelope is the defense against polished misinformation.

## Storage strategy

- Raw events: append-only, retained indefinitely for personal local use.
- Atomic ledger: idempotent by source/account/external identity.
- Position snapshots: point-in-time observations retained for reconciliation.
- Market snapshots: append-only with configurable retention for intraday observations.
- Derived series/read models: rebuildable and method-versioned.
- Workspace preferences: mutable, versioned, and isolated from financial records.

## Delivery sequence

### Foundation checkpoint

- instrument master with adjusted-deliverable support;
- execution, cash movement, and option lifecycle tables;
- underlying/option point-in-time market snapshots;
- ports, repositories, ingestion services, migrations, and invariant tests;
- zero changes to the current demo surface except compatibility fixes.

### Live truth checkpoint

- Schwab transaction source adapter once approved documentation/payloads are available;
- CSV fallback importer through the same normalized contracts;
- deterministic lifecycle pairing and position/cash reconciliation;
- Records workspace backed by real data with raw-source drill-through.

### Operator checkpoint

- open-contract projection, risk concentrations, quote quality, catalyst rules, and scenarios;
- cash/realized/open attribution, stock-only baseline, and campaign economics;
- saved layouts, command navigation, exports, and accessibility controls.

### Research checkpoint

- scheduled market observations, normalized IV series, realized volatility, skew/term structure;
- entry/exit context, forward studies, cohorts, and rule journal.

## Cross-system invariants

- One instrument identity is used by positions, executions, lifecycle events, and quotes.
- One accounting sign convention is used everywhere.
- Source timestamps are never replaced by ingestion timestamps.
- Missing values never become zeros.
- Estimates never become observed facts through aggregation.
- Campaigns, baselines, and scenarios never mutate ledger truth.
- Read models can be rebuilt; raw and normalized atomic records cannot be edited away.
- No broker adapter can place an order; the product is read-only analytics.

## Scope control

The approved destination is broad, but the default UI remains narrow. New metrics earn space only if
they change a decision, explain an outcome, expose a risk, or prove the source. Specialized detail
belongs in its workspace, not in another same-weight dashboard card.

## Verification pyramid

1. Domain invariant tests for quantities, signs, timestamps, deliverables, and quote quality.
2. Repository/migration tests for exact persistence, idempotency, and referential integrity.
3. Service tests for raw-first ingestion, reconciliation, and reproducible calculations.
4. API contract tests for status/method/provenance metadata.
5. Browser tests for information hierarchy, keyboard behavior, reflow, and visual regressions.
6. Reconciliation against independent broker statements before trusting live totals.

## Immediate implementation boundary

This checkpoint implements only the shared atomic spine. It deliberately does not invent Schwab
transaction fields before approved documentation or real payloads are available, and it does not
wire demo figures into the new tables. The next adapters will populate the spine without changing
its consumers.
