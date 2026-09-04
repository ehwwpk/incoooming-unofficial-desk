# Incoooming architecture

## Target outcome

Incoooming is one local process: get real Schwab, CSV, or demo book data into an auditable ledger
with the least moving parts, while keeping transaction history, campaign accounting, roll planning,
and IV analytics behind explicit boundaries.

## Runtime shape

```text
CLI / source gateway / local web UI
        |
application services
        |
domain contracts and ports
   /                 \
source adapters       SQLite repositories
   |                       |
Schwab OAuth/API      append-only raw events + derived snapshots
CSV staging parser    isolated imported books
Radar market port     isolated lookup runs + candidate evidence
```

This is a modular monolith: one local process and one database, with explicit internal boundaries. A service split would slow the personal-use milestone without improving correctness.

The live process owns one serialized full-sync coordinator. It runs once shortly after server
startup, repeats on a bounded interval, and accepts manual refresh requests through the same lock.
Browser GET requests remain read-only projections over SQLite; they never wait on Schwab directly.

Demo mode is a separate read adapter implementing the same dashboard contract. It does not call Schwab, create sync runs, or write SQLite records. Removing demo mode later will not change the API or templates.

CSV imports are immutable source datasets. Each import stages files and normalized records under a
dataset identifier, then projects that dataset through the same dashboard contract. Selecting a CSV
book changes the reader; it never copies rows into or combines them with the live Schwab ledger.

Premium Radar has a separate market-data gateway, HTTP client, cache, persistence tables, and
explicit request route. It may read the active dashboard snapshot for account context, but it is not
registered with the recurring account sync coordinator.

## Module responsibilities

| Module | Owns | Must not own |
|---|---|---|
| `domain` | Broker-neutral account/position values and reconciliation concepts | HTTP, SQLAlchemy, FastAPI |
| `application` | Use cases, ports, and deterministic dashboard alert rules | Schwab JSON details, table mappings |
| `infrastructure/schwab` | OAuth, token refresh, read-only HTTP calls, Schwab payload mapping | Ledger calculations or UI |
| `infrastructure/database` | SQLAlchemy tables, unit of work, repositories, migrations | Schwab HTTP or presentation logic |
| `api` | Local JSON/HTML routes and dependency access | Direct database queries or broker parsing |
| `web` | Templates, chart coordinate projection, interaction, and static assets | Alert thresholds, accounting, broker rules |

## Live data flow

1. Create a `schwab_full` sync run in `running` state and acquire the in-process sync lock.
2. Request the account-number/hash mapping and accounts with positions from Schwab.
3. Store immutable raw account events before normalizing point-in-time account, balance, and position snapshots.
4. Fetch one year of transaction history in bounded windows and normalize executions, cash movements, and lifecycle events.
5. Fetch current underlying quotes, bounded option chains and Greeks for held short-option
   underlyings, plus daily underlying history. Duplicate daily or minute candles inside one raw
   history response keep the last revision so a reprint cannot abort the refresh.
6. Commit each auditable ingestion stage and its reconciliation evidence.
7. Mark `schwab_full` completed only after all stages succeed. Any exception persists a failed full run, remains visible in the UI, and does not replace the latest known-good full snapshot.

Dashboard and workspace GET routes reread that stored ledger. They do not call Schwab. Roll math
walks the stored chain for those short-option underlyings, not only the open OCC symbols.

## Extension points

- Transactions are stored as raw events and normalized into executions, cash movements, and
  lifecycle events.
- CSV imports remain isolated books. Moving them into the canonical live ledger would require
  broker-specific reconciliation against account snapshots.
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
