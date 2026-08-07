# ADR 0001: local-first modular monolith

**Status:** Accepted for Phase 0/1
**Date:** 2026-08-07

## Context

The product has one user and needs to reach a live Schwab account quickly. The difficult problem is accounting correctness and source reconciliation, not distributed-system scale.

## Decision

Use Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, SQLite, server-rendered HTML, and a CLI in one repository and process. Enforce domain, application, infrastructure, and presentation boundaries inside that process.

## Consequences

- Setup and debugging remain local and fast.
- SQLite is sufficient for a single writer and can be backed up as one file.
- The browser UI can later be replaced without changing ingestion or accounting logic.
- Large option-chain history can move to Parquet/DuckDB without moving the ledger.
- Remote access, multiple users, and order execution are explicitly out of scope.
