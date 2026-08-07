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
- Exercises a personalized but fictional 13-week book: 700 CVX, 800 KTOS, and 500 URNM shares.
- Keeps every mock call 15–40% above the underlying at sale and 21–56 days to expiration.
- Derives premium, buyback, net cash, coverage, and lifecycle totals from execution records.
- Never calls Schwab, creates a sync run, or writes to SQLite.
- Uses the same API serializer, Jinja templates, and display formatters as live mode.

## Stable view sections

1. Combined portfolio: net value, quarter option cash, total cash income, coverage, calls sold, and shares called away.
2. Underlying attribution: shares, market value, per-name option cash, price/sale rhythm, lifecycle, strike gap, DTE, and open calls.
3. Income: 13 weekly periods with option cash and dividends reconciled to quarter totals.
4. Lifecycle: contracts expired, closed, rolled, and still open, plus assignments and completed-trade win rate.
5. Campaigns: current legs, dates, quarter option cash, open profit/loss, collateral, and return on capital.
6. Call ledger: sale date, expiry, DTE, quantity, sale-time spot, strike, gap, premium, buyback, net cash, outcome, and sale signal.
7. Positions and risk: reconciled inventory, buying-power use, delta, theta, concentration, and next expiration.

## Accounting definitions

- Gross premium is `premium per share × contracts × 100`.
- Net option cash is gross premium minus buy-to-close cash outflow.
- Total cash income is net option cash plus dividends.
- Realized option income includes only completed tickets; open-call credit remains visible separately.
- Rolled tickets preserve the close debit on the old call and the new sale as separate execution records.
- Active coverage is open contracts divided by share-backed contract capacity.

## Replacement path

The next ledger slice will normalize executions and cash movements. Campaign accounting will consume those normalized events and populate the existing income and campaign fields. Market-data ingestion will later supply marks and Greeks to the existing position and risk fields. Neither step requires a route or template rewrite.
