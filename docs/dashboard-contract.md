# Dashboard contract

## Purpose

The browser and JSON API consume one typed dashboard snapshot regardless of data source. This lets the UX evolve during Schwab approval without coupling templates to mock fixtures or Schwab response shapes.

## Source modes

### Live ledger

- Reads reconciled account and position snapshots from repository ports.
- Shows only values supported by stored broker observations.
- Returns empty income and campaign collections until execution ingestion exists.
- Never substitutes fictional analytics for missing live data.

### Demo

- Returns deterministic, clearly labeled fictional values from an isolated adapter.
- Exercises equities, multi-leg options, income periods, campaigns, allocation, and risk views.
- Never calls Schwab, creates a sync run, or writes to SQLite.
- Uses the same API serializer, Jinja templates, and display formatters as live mode.

## Stable view sections

1. Portfolio summary: net value, cash, invested value, daily change.
2. Income: weekly series plus week, month, quarter, and year-to-date totals.
3. Campaigns: strategy, legs, dates, income, open profit/loss, collateral, and return on risk.
4. Positions: account mask, instrument, strategy, quantity, prices, market value, and daily change.
5. Allocation: labeled capital slices and percentages.
6. Risk: buying-power use, delta, theta, short-contract count, concentration, and next expiration.

## Replacement path

The next ledger slice will normalize executions and cash movements. Campaign accounting will consume those normalized events and populate the existing income and campaign fields. Market-data ingestion will later supply marks and Greeks to the existing position and risk fields. Neither step requires a route or template rewrite.
