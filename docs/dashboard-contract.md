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
- Exercises a personalized but fictional 13-week option book over 700 CVX, 800 KTOS, and 500 URNM shares.
- Uses frozen, unadjusted Yahoo Finance daily closes retrieved on August 7, 2026 for the underlying price paths. These are real market-session observations; the option executions, marks, IV, and Greeks remain clearly simulated.
- Keeps every mock call 15–40% above the underlying at sale and 21–56 days to expiration.
- Derives premium received, executed close/roll debits, net premium cash flow, coverage, and lifecycle totals from execution records.
- Never calls Schwab, creates a sync run, or writes to SQLite.
- Uses the same API serializer, Jinja templates, and display formatters as live mode.

## Stable view sections

1. Combined portfolio: net value, selected-window net premium cash, total strategy income, coverage, calls sold, and shares called away.
2. Underlying attribution: selected-window option income/APR/dividends/capture, a 13-week observed daily-close path with faint Friday guides and numbered simulated lifecycle event markers that map directly to a written event tape, and per-contract premium-received/current-option-value/open-P&L economics.
3. Strategy intelligence: deterministic internal exceptions derived from the tracked book (marks versus credit, dividend-calendar overlap, IV/Greek dispersion, and covered-lot capacity). It never embeds financial-news or social-headline content.
4. Income: 13 weekly periods with option cash and dividends reconciled to quarter totals.
5. Lifecycle: contracts expired, closed, rolled, and still open, plus assignments and the completed-ticket positive-cash rate.
6. Campaigns: current legs, dates, quarter option cash, open profit/loss, collateral, and return on capital.
7. Call ledger: sale date, expiry, DTE, quantity, sale-time spot, strike, gap, premium, executed close debit, net cash, outcome, and sale signal.
8. Positions and risk: reconciled inventory, buying-power use, delta, theta, concentration, and next expiration.

The default workspace keeps decision surfaces visible and moves verbose records into one collapsed detail area. “Active books,” “Call history,” and “Positions” are tabs inside that area; only one record view renders visibly at a time.

## Performance windows

- Week uses the latest seven calendar days.
- Month uses a rolling 28-day view so partial calendar months do not distort the first comparison.
- Month is the default screen window; changing the performance control updates the combined portfolio summary and window metadata from the same state.
- The week/month/quarter/year control lives in the top operating header because it governs the full desk context. The accounting sheet below explains the selected window instead of owning the control.
- Per-name windows reconcile option cash, dividends, gross premium, and executed buy-to-close debits back to the selected portfolio window. Static inventory, live-risk fields, and the 13-week price/execution tape do not pretend to change with that selection.
- Quarter uses the current detailed 13-week ledger window.
- Calendar YTD runs from January 1 through the snapshot date.
- Rolling 365 uses the trailing 365 calendar days and is intentionally separate from YTD.
- The year control exposes both YTD and rolling-365 totals; completed-quarter bars provide trend context but do not claim to reconcile a partial current quarter to 365 days.
- The selected window reports transaction cash: premium received minus executed close/roll debits equals net premium cash flow; net premium cash flow plus dividends equals total strategy income.
- Calendar-month pace is a comparison metric, not additional cash. It equals net premium cash flow divided by elapsed days and scaled to `365 / 12` days. For example, a 28-day total can differ from its normalized 30.4-day pace.
- APR equals window cash divided by current stock market value and annualized by actual window days. It is not total return and can be distorted by short windows.

## Manager objective

- The default target is $3,000 per month of net premium cash; dividends are shown separately and do not count toward target attainment.
- The target is editable from $100 to $1,000,000 and persists in local browser storage for this private installation. Changing it recalculates window pace, rolling-year progress, target gap, and historical months hit.
- The objective view reports rolling 4-week cash, 13-week monthly run-rate, YTD monthly run-rate, and rolling-365 monthly average together.
- “Entry-rule fit” means only that a mock ticket fits the current personal rules: 15–40% above sale-time spot and 21–56 DTE. It is a discipline measure, not a risk score, safety claim, or probability of profit.
- Coverage, concentration, strike buffer, average DTE, premium capture, and executed-debit drag remain separate inputs so the UI does not hide risk inside one opaque rating.

## Accounting definitions

- Gross premium is `premium per share × contracts × 100`.
- Net premium cash flow is gross premium minus executed buy-to-close cash outflow. It describes cash transactions, not mark-to-market profit.
- Total cash income is net premium cash flow plus dividends.
- Completed-ticket option income excludes open calls; open-call credit remains visible separately.
- The open-book reconciliation shows credit already received, current open-call value, and open P/L at the current mark. A current mark is an estimate, not an executed close debit or a forecast of the expiry outcome.
- Rolled tickets preserve the close debit on the old call and the new sale as separate execution records.
- Active coverage is open contracts divided by share-backed contract capacity.
- Premium capture is net premium cash flow divided by gross premium; executed-debit drag is executed buy-to-close cash divided by gross premium.
- The lifetime basis lens subtracts tracked option and dividend cash from original purchase cost for a private “capital earned back” view. Below 100% it shows original capital remaining. At or above 100% it shows a positive surplus beyond original cost instead of asking the user to interpret a negative adjusted basis. It never changes brokerage or tax-lot cost basis.
- Demo IV and delta values are explicitly marked simulated. Live values will be quantity-weighted from current open-call contracts after Schwab market-data access is approved.
- Each open call compares premium received with current option value and derives open P/L, credit capture, intrinsic value, and remaining time value. Open P/L can be negative when the option mark rises above its sale price; the dashboard does not frame that mark as a buyback recommendation.
- Demo charts use an explicit frozen close for each observed market session; they never interpolate between weekly anchors. Each simulated call ticket uses the observed close on its sale date, and its strike remains 15–40% above that close. Numbered sale markers reconcile one-for-one to call-history records and a visible event tape, while expired, closed, rolled, and assigned markers reconcile to completed records. Live charts will replace the frozen fixture with Schwab market-data observations.
- Per-contract DTE and short-position theta remain supporting context. Demo theta is explicitly simulated and reconciles to portfolio daily theta. Calendar time elapsed is `days since sale / original days from sale to expiry`; it is intentionally separate from theta and option-value decay. The time-value pace is a simple current-time-value/current-theta ratio, not forecast income or a decay schedule.
- Assignment is tracked separately as assigned contracts and shares called away; current share inventory can include shares reacquired after a historical assignment. Assignment is a disposition, not automatically a failed trade: a planned exit also reports its effective sale price (strike plus premium per share), underlying gain to strike, and foregone upside separately when execution data is available.
- A dividend-overlap monitor appears when an open call expires on or after the next ex-dividend date. The overlap is a calendar screen, not an assignment prediction; live evaluation must also consider moneyness and remaining extrinsic value.

## Return and hurdle framing

- Premium APR and total-income APR are cash-yield views, not total portfolio return. They must not be presented as a like-for-like comparison with a Treasury yield without underlying price change, capped upside, dividends, and assignment outcomes.
- A future configurable hurdle view will compare mark-adjusted covered-call total return with a selected Treasury tenor and an equity benchmark. The risk-free rate will come from dated source data rather than a hard-coded “safe 4%” assumption.
- The dashboard will keep assignment economics and opportunity cost separate: being called away at an acceptable effective sale price can be intentional even when the stock later trades higher.

## Replacement path

The next ledger slice will normalize executions and cash movements. Campaign accounting will consume those normalized events and populate the existing income and campaign fields. Market-data ingestion will later supply marks and Greeks to the existing position and risk fields. Neither step requires a route or template rewrite.
