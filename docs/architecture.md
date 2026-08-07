# Phase 0/1 architecture

## Target outcome

Get real Schwab account and position data into an auditable local ledger with the least moving parts, while preserving boundaries needed for transaction history, campaign accounting, and IV analytics.

## Runtime shape

```text
CLI / local web UI
        |
application services
        |
domain contracts and ports
   /                 \
Schwab read adapter   SQLite repositories
   |                       |
Schwab OAuth/API      append-only raw events + derived snapshots
```

This is a modular monolith: one local process and one database, with explicit internal boundaries. A service split would slow the personal-use milestone without improving correctness.

Demo mode is a separate read adapter implementing the same dashboard contract. It does not call Schwab, create sync runs, or write SQLite records. Removing demo mode later will not change the API or templates.

## Module responsibilities

| Module | Owns | Must not own |
|---|---|---|
| `domain` | Broker-neutral account/position values and reconciliation concepts | HTTP, SQLAlchemy, FastAPI |
| `application` | Use cases and ports: sync, status, repository and broker contracts | Schwab JSON details, table mappings |
| `infrastructure/schwab` | OAuth, token refresh, read-only HTTP calls, Schwab payload mapping | Ledger calculations or UI |
| `infrastructure/database` | SQLAlchemy tables, unit of work, repositories, migrations | Schwab HTTP or presentation logic |
| `api` | Local JSON/HTML routes and dependency access | Direct database queries or broker parsing |
| `web` | Templates and static assets | Domain rules |

## Initial data flow

1. Create a `sync_run` in `running` state.
2. Request the account-number/hash mapping and accounts with positions from Schwab.
3. Store one immutable raw event per returned account before normalization.
4. Map the response into broker-neutral account and position values.
5. Upsert the account identity using the Schwab account hash; persist a point-in-time position snapshot.
6. Reconcile duplicate/malformed position identities and persist issues.
7. Commit the unit of work and mark the run completed. Any failure rolls back normalized writes and records a failed run in a separate transaction.

## Near-term extension points

- Transactions become another raw event type and normalization service.
- CSV imports implement the same broker-event ingestion port.
- Campaigns consume normalized executions; they never parse Schwab payloads.
- Quotes and chains use a separate market-data port and storage policy.
- A replacement UI consumes the same local API; it does not require ledger changes.

## Refactor guardrails

- Raw broker JSON remains immutable and parser-versioned.
- Money and quantities use `Decimal`, never binary floating point.
- Database migrations are required from the first schema.
- Every sync is identified, timestamped, and replayable.
- Schwab account hashes, not visible account numbers, are durable external keys.
- Unknown payload fields are retained in raw JSON; unknown required shapes fail loudly.
- Local UI routes call application services, never repositories directly.
