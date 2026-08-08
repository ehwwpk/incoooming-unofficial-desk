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

1. Combined portfolio: net value, selected-window option cash, total cash income, coverage, calls sold, and shares called away.
2. Underlying attribution: selected-window option cash/APR/dividends/capture, market context, per-contract DTE/theta clocks, and explicitly labeled 13-week execution history.
3. Income: 13 weekly periods with option cash and dividends reconciled to quarter totals.
4. Lifecycle: contracts expired, closed, rolled, and still open, plus assignments and completed-trade win rate.
5. Campaigns: current legs, dates, quarter option cash, open profit/loss, collateral, and return on capital.
6. Call ledger: sale date, expiry, DTE, quantity, sale-time spot, strike, gap, premium, buyback, net cash, outcome, and sale signal.
7. Positions and risk: reconciled inventory, buying-power use, delta, theta, concentration, and next expiration.

## Performance windows

- Week uses the latest seven calendar days.
- Month uses a rolling 28-day view so partial calendar months do not distort the first comparison.
- Month is the default screen window; changing the performance control updates the combined portfolio summary and window metadata from the same state.
- Per-name windows reconcile option cash, dividends, gross premium, and buy-to-close cost back to the selected portfolio window. Static inventory, live-risk fields, and the 13-week price/execution tape do not pretend to change with that selection.
- Quarter uses the current detailed 13-week ledger window.
- Calendar YTD runs from January 1 through the snapshot date.
- Rolling 365 uses the trailing 365 calendar days and is intentionally separate from YTD.
- The year control exposes both YTD and rolling-365 totals; completed-quarter bars provide trend context but do not claim to reconcile a partial current quarter to 365 days.
- Monthly run-rate equals net option cash divided by elapsed days and scaled to `365 / 12` days.
- APR equals window cash divided by current stock market value and annualized by actual window days. It is not total return and can be distorted by short windows.

## Manager objective

- The default target is $3,000 per month of net option cash; dividends are shown separately and do not count toward target attainment.
- The target is editable from $100 to $1,000,000 and persists in local browser storage for this private installation. Changing it recalculates window pace, rolling-year progress, target gap, and historical months hit.
- The objective view reports rolling 4-week cash, 13-week monthly run-rate, YTD monthly run-rate, and rolling-365 monthly average together.
- “Safe-rule compliance” means only that a mock ticket fits the current personal rules: 15–40% above sale-time spot and 21–56 DTE. It is a discipline measure, not a risk score, safety claim, or probability of profit.
- Coverage, concentration, strike buffer, average DTE, premium capture, and buyback drag remain separate inputs so the UI does not hide risk inside one opaque rating.

## Accounting definitions

- Gross premium is `premium per share × contracts × 100`.
- Net option cash is gross premium minus buy-to-close cash outflow.
- Total cash income is net option cash plus dividends.
- Realized option income includes only completed tickets; open-call credit remains visible separately.
- Rolled tickets preserve the close debit on the old call and the new sale as separate execution records.
- Active coverage is open contracts divided by share-backed contract capacity.
- Premium capture is net option cash divided by gross premium; buyback drag is buy-to-close cash divided by gross premium.
- The lifetime basis lens subtracts tracked option and dividend cash from original purchase cost for a private “capital earned back” view. It never changes brokerage or tax-lot cost basis.
- Demo IV and delta values are explicitly marked simulated. Live values will be quantity-weighted from current open-call contracts after Schwab market-data access is approved.
- Each open-call clock shows its own DTE, remaining extrinsic value, and short-position theta benefit. Demo theta is explicitly simulated and reconciles to portfolio daily theta. It is a theoretical one-day sensitivity with other pricing inputs held equal, not forecast income.
- A dividend-overlap monitor appears when an open call expires on or after the next ex-dividend date. The overlap is a calendar screen, not an assignment prediction; live evaluation must also consider moneyness and remaining extrinsic value.

## Replacement path

The next ledger slice will normalize executions and cash movements. Campaign accounting will consume those normalized events and populate the existing income and campaign fields. Market-data ingestion will later supply marks and Greeks to the existing position and risk fields. Neither step requires a route or template rewrite.
