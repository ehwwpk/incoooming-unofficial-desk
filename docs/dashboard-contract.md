# Dashboard contract

## Purpose

The browser and JSON API consume one typed dashboard snapshot regardless of data source. This keeps
the interface independent from demo fixtures and Schwab response shapes while the live ledger grows.

## Source modes

### Live ledger

- Reads reconciled account and position snapshots from repository ports.
- Shows only values supported by stored broker observations.
- Returns empty income and campaign collections until execution ingestion exists.
- Never substitutes fictional analytics for missing live data.

### Demo

- Returns deterministic, clearly labeled fictional values from an isolated adapter.
- Uses `DEMO CHECKED` for internally reconciled fixtures; only live broker-backed state may display `RECONCILED`.
- Exercises a personalized but fictional quarterly option book over 700 CVX, 800 KTOS, and 500 URNM shares.
- Uses frozen, unadjusted Yahoo Finance daily closes retrieved on August 7, 2026 for the underlying price paths. These are real market-session observations; the option executions, marks, IV, and Greeks remain clearly simulated.
- Keeps every mock call 15–40% above the underlying at sale and 21–56 days to expiration.
- Derives premium received, executed close/roll debits, net premium cash flow, coverage, and lifecycle totals from execution records.
- Never calls Schwab, creates a sync run, or writes to SQLite.
- Uses the same API serializer, Jinja templates, and display formatters as live mode.

## Stable view sections

1. Combined portfolio: net value, selected-window net premium cash, total strategy income, coverage, calls sold, and shares called away.
2. Underlying attribution: selected-window option income/APR/dividends/capture, an observed daily-close path with `16W`, `8W`, and `4W` date ranges, campaign markers that map to auditable execution detail, and per-contract premium-received/current-option-value/open-P&L economics. The campaign renderer and its reconciliation rules are documented in [Option campaign chart redesign](product/option-campaign-chart-redesign.md).
3. Income: a quarterly window with 13 weekly periods reconciled to the quarter total.
4. Lifecycle: contracts expired, closed, rolled, and still open, plus assignments and the completed-ticket positive-cash rate.
5. Campaigns: current legs, dates, quarter option cash, open profit/loss, collateral, and return on capital.
6. Call ledger: sale date, expiry, DTE, quantity, sale-time spot, strike, gap, premium, executed close debit, net cash, outcome, and sale signal.
7. Positions and risk: reconciled inventory, buying-power use, delta, theta, concentration, and next expiration.

The default Desk keeps the operating answer visible and folds stock detail until the operator asks
for it. The Open Options workspace follows the same rule: portfolio totals remain visible, while the
expiration calendar and grouped contract register start closed and open from their full headers.
Contract rows provide a second disclosure level for clocks, quotes, Greeks, value mix, and liquidity.

The primary workspace does not reserve a generic news or telemetry rail. A derived exception earns visible space only when it is actionable and can be placed next to the affected security or contract.

### Nibwick desk notes

Nibwick is a small bear clerk. Round ears, a broad head, a centered nose, paws, and feet remain stable across patrol and reaction poses. The popup contains one animated ledger scene; every frame preserves that silhouette while the eyes, paws, and page carry the movement.

The note is a terminal worksheet rather than a consumer modal:

- A 56px command strip carries the `NWK` function code, security, position, ledger scene, and close command in one row.
- The security, headline, severity, and plain-English evidence use the full worksheet width.
- Each fact cell separates its primary value from its qualifier so numbers align instead of forming display cards.
- Methodology and limitations remain available in a collapsed disclosure rather than occupying the default decision surface.
- Previous, next, and security-jump commands share one footer.
- The surface uses two interior charcoal tones, one grid-line tone, and an amber perimeter.

The panel is conditional and initially hidden, so alerts reserve no permanent dashboard space. Entering a flagged security workspace can make Nibwick wave and mark the badge, but it never opens the note automatically. The badge reports unread notes—not the lifetime alert total—and disappears after every current note has been viewed in the browser session. Opening the note pauses the patrol, marks the active note read, and subtly links the affected security workspace. Close, outside-click, and Escape paths remain available. Reduced-motion users receive a static reading pose.

Alert severity, facts, thresholds, and method notes come from typed application rules. Nibwick changes presentation, not the underlying decision logic, and never invents advice.

## Performance windows

- The primary selector is 4W, QTR, YTD, and R365. Daily source detail remains available inside each
  period without turning every day into a top-level performance window.
- 4W uses a rolling 28-day view so partial calendar months do not distort the first comparison and is
  the default operating window.
- The control lives in the top Desk header because it governs the full operating context. Supporting
  accounting explains the selected window instead of owning the control.
- Per-name windows reconcile option cash, dividends, gross premium, and executed buy-to-close debits back to the selected portfolio window. Static inventory, live-risk fields, and the quarterly price/execution tape do not pretend to change with that selection.
- Quarterly uses the current rolling 13-week detailed ledger window.
- Calendar YTD runs from January 1 through the snapshot date.
- Rolling 365 uses the trailing 365 calendar days and is intentionally separate from YTD.
- When rolling 365 is active, the two F1 income cells show explicit one-month averages for net premium cash and total strategy income. Each is the 365-day total divided by 12; the values are context, not additional cash.
- The year control exposes both YTD and rolling-365 totals; completed-quarter bars provide trend context but do not claim to reconcile a partial current quarter to 365 days.
- The selected window reports transaction cash: premium received minus executed close/roll debits equals net premium cash flow; net premium cash flow plus dividends equals total strategy income.
- Calendar-month pace is a comparison metric, not additional cash. It equals net premium cash flow divided by elapsed days and scaled to `365 / 12` days. For example, a 28-day total can differ from its normalized 30.4-day pace.
- APR equals window cash divided by current stock market value and annualized by actual window days. It is not total return and can be distorted by short windows.

Daily cash and daily theta are never interchangeable. Cash appears only on execution, fee, or dividend dates. Theta is a model sensitivity for the open option book under unchanged-input assumptions.

## Performance without a target gauge

- The default Desk reports realized results and normalized pace without grading them against a
  user-entered monthly target.
- Rolling 4-week cash, quarterly pace, YTD pace, and rolling-365 monthly average remain available as
  observations. They are not promises, quotas, or encouragement to sell another option.
- Risk and obligation context earns space before motivational progress graphics.
- “Entry-rule fit” means only that a mock ticket fits the current personal rules: 15–40% above sale-time spot and 21–56 DTE. It is a discipline measure, not a risk score, safety claim, or probability of profit.
- Coverage, concentration, strike buffer, average DTE, premium capture, and executed-debit drag remain separate inputs so the UI does not hide risk inside one opaque rating.

## Accounting definitions

- Live `TODAY` change is current Schwab liquidation value minus Schwab's start-of-day liquidation value and minus normalized same-market-day external transfers. The market day is derived in America/New_York, not from the UTC date or the host computer's local date. Deposits and withdrawals are disclosed beside the result but are never called profit or loss. The adjusted dollar result is divided by the start-of-day liquidation value. Position-level day P/L is only a fallback when account-level values are unavailable; the header never mixes a position sum with an unrelated account-value denominator.
- Gross premium is `premium per share × contracts × 100`.
- Net premium cash flow is gross premium minus executed buy-to-close cash outflow. It describes cash transactions, not mark-to-market profit.
- Total cash income is net premium cash flow plus dividends.
- Completed-ticket option income excludes open calls; open-call credit remains visible separately.
- The open-book reconciliation shows credit already received, current open-call value, and open P/L at the current mark. A current mark is an estimate, not an executed close debit or a forecast of the expiry outcome.
- Rolled tickets preserve the close debit on the old call and the new sale as separate execution records.
- Active coverage is open contracts divided by share-backed contract capacity.
- Short puts remain in the same per-underlying option book as short calls. Portfolio open-option counts, open mark P/L, next expiration, and model theta include both sides, while share-lot coverage remains a call-only ratio so puts never masquerade as covered shares.
- Premium capture is net premium cash flow divided by gross premium; executed-debit drag is executed buy-to-close cash divided by gross premium.
- The lifetime basis lens subtracts tracked option and dividend cash from original purchase cost for a private “capital earned back” view. Below 100% it shows original capital remaining. At or above 100% it shows a positive surplus beyond original cost instead of asking the user to interpret a negative adjusted basis. It never changes brokerage or tax-lot cost basis.
- Demo IV and delta values are explicitly marked simulated. Live values will be quantity-weighted from current open-call contracts after Schwab market-data access is approved.
- Each open call compares premium received with current option value and derives open P/L, credit capture, intrinsic value, and remaining time value. Open P/L can be negative when the option mark rises above its sale price; the dashboard does not frame that mark as a buyback recommendation.
- The option-value reference track devotes its full scale to 0â€“100% of entry credit. Values above entry credit fill the reference track and report the exact excess separately; cards never rescale independently. Historical event popups use current mark for open calls, actual closing debit for closed or rolled calls, zero for expiration, and omit this comparison for assignment.
- Each open call shows signed dollar and percentage distance from the current underlying price to its strike beside DTE. An out-of-the-money call reads `TO STRIKE`; an in-the-money call reads `PAST STRIKE` so proximity never depends on color or mental subtraction.
- A compact nearest-call link addresses the exact contract, opens its collapsed underlying automatically, centers the contract in view, and moves keyboard focus to that contract. It never stops at an unopened stock summary.
- Demo charts use an explicit frozen close for each observed market session; they never interpolate between weekly anchors. Each simulated call ticket uses the observed close on its sale date, and its strike remains 15–40% above that close. Numbered sale markers reconcile one-for-one to call-history records and a visible event tape, while expired, closed, rolled, and assigned markers reconcile to completed records. Live charts will replace the frozen fixture with Schwab market-data observations.
- Chart range changes remap the close line, daily points, Friday guides, option events, share events, axes, lifecycle links, and visible-event ledger from the same raw dates and prices. The date range and market-session count are explicit. Focus mode is an inline enlargement with an Escape-key exit; it does not scale a raster or claim more history than the selected range contains.
- Per-contract DTE and short-position theta remain supporting context. Demo theta is explicitly simulated and reconciles to portfolio daily theta. Calendar time elapsed is `days since sale / original days from sale to expiry`; it is intentionally separate from theta and option-value decay. The time-value pace is a simple current-time-value/current-theta ratio, not forecast income or a decay schedule.
- Assignment is tracked separately as assigned contracts and shares called away; current share inventory can include shares reacquired after a historical assignment. Assignment is a disposition, not automatically a failed trade: a planned exit also reports its effective sale price (strike plus premium per share), underlying gain to strike, and foregone upside separately when execution data is available.
- A dividend-overlap note appears when an open call expires on or after a nearby ex-dividend date. It reports the closest strike, the call's current time value per share, dividend/time-value ratio, and a pre-dividend gray line equal to strike plus indicated dividend. The gray line is the price needed to remain near the strike after a dividend-sized adjustment; it is not a price forecast. Severity can increase only when the call is in the money and the dividend exceeds remaining time value per share. This is still a screening heuristic, not an assignment prediction.
- A fast-move note compares the latest close with five trading sessions earlier and the nearest open strike. It reports dollar and percentage distance to strike, covered-share distance, current mark versus entry credit, DTE, and a transparent 0–100 roll-review pressure heuristic. The score never claims to estimate assignment odds or expected roll profitability and does not tell the user to roll or close.

## Return and hurdle framing

- Premium APR and total-income APR are cash-yield views, not total portfolio return. They must not be presented as a like-for-like comparison with a Treasury yield without underlying price change, capped upside, dividends, and assignment outcomes.
- A future configurable hurdle view will compare mark-adjusted covered-call total return with a selected Treasury tenor and an equity benchmark. The risk-free rate will come from dated source data rather than a hard-coded “safe 4%” assumption.
- The dashboard will keep assignment economics and opportunity cost separate: being called away at an acceptable effective sale price can be intentional even when the stock later trades higher.

## Replacement path

The next ledger slice will normalize executions and cash movements. Campaign accounting will consume those normalized events and populate the existing income and campaign fields. Market-data ingestion will later supply marks and Greeks to the existing position and risk fields. Neither step requires a route or template rewrite.
