# Approved pre-Schwab operator plan

Status: fixture-backed operator phase implemented and verified on August 10, 2026. This document scopes the work completed with deterministic fixtures before live Schwab payloads are available. Live-source items at the end remain intentionally unavailable until their mappings can be verified.

## Product promise

The first screen must answer four questions without requiring interpretation:

1. How much net option cash and dividend cash did the strategy generate?
2. What shares are currently committed to open calls?
3. Which position deserves attention now, and why?
4. Did active management improve the result versus simply holding the shares?

The desk serves a covered-call seller and dividend collector. It is not a generic trading terminal, an order-entry system, or a leaderboard for maximizing premium.

## Primary information architecture

Only three surfaces are primary:

- **Desk:** selected-period cash, observed pace, live obligations, per-name state, and one actionable exception.
- **Open Calls:** the contract register and expandable obligation, market, economics, event, and campaign detail.
- **Results:** monthly ledger, campaign outcomes, assignments, capital recovery, and stock-only attribution.

Volatility research, the complete activity ledger, imports, and Data Health remain tools. Data Health is maintenance reached from source status or the Tools menu; it is not a daily peer of the operator surfaces.

## Period decision

The primary selector will use **4W, QTR, YTD, and R365**. The standalone 1W top-level window will be removed.

Daily data is preserved; it is not confused with a separate daily performance window:

- The Desk uses a compact activity tape with only the latest nonzero executions in the selected window.
- QTR comparison defaults to weekly totals with exact dated events available in Records.
- YTD and R365 comparison defaults to monthly totals with exact dated events available in Records.
- Underlying price paths continue to use real daily market sessions.
- Days without an execution or dividend remain valid ledger dates but are not rendered as empty activity.
- Model theta per day is an option-price sensitivity estimate, not daily income and not a cash forecast.

The current 1W fixture and calculations may remain internally available for tests and record queries, but they will not occupy primary navigation.

## Strategy intent is per name and per tranche

A single global definition of a safe covered call is not valid. Policy attaches to an underlying and, when useful, to a particular share tranche.

Each tranche can declare:

- share-retention intent: preserve shares, neutral, acceptable exit, or intentional trim/redeployment;
- acceptable effective exit price;
- preferred DTE band and minimum strike buffer;
- optional delta and liquidity limits when live data supports them;
- earnings and dividend restrictions;
- maximum shares covered;
- entry-context preferences such as range position, price rollover, and volatility expansion.

The UI exposes which rules are met or missed. It does not compress them into an unexplained safety or probability score.

### Personalized fixture direction

The next fixture revision should model the user's process without pretending to reproduce the real account:

- **KTOS / upside preservation:** calls centered on $75 with roughly 2–5 weeks to expiry, plus farther $90 calls with roughly 6–8 weeks to expiry. The purpose is to collect premium while leaving materially more upside room than the current fictional $65 call.
- **CVX / staged exit and capital redeployment:** nearer $195 and $205 calls with roughly 2–3 weeks to expiry, plus farther $215 calls with roughly 6–8 weeks to expiry. A limited number of shares may intentionally be called away when the resulting cash can be redeployed.
- **URNM:** retain the existing higher-strike, income-oriented posture until the user supplies a more specific policy.

Exact contract quantities, sale dates, premiums, and current marks must not be inferred from these ranges. The fixture implementation will preserve the known 700 CVX, 800 KTOS, and 500 URNM share inventory and will use explicit fictional labels.

## Locked work sequence

### Batch A — simplify the current experience

- Remove 1W from the primary period control and make the cash chart follow the selected period.
- Standardize position, contract, and covered-share terminology.
- Replace passive dividend overlap counts with time-sensitive assignment diagnostics.
- Keep Nibwick closed and exception-driven; ordinary future events do not create unread notes.
- Collapse permanent accounting explainers after their meaning is available through labels, help, or drill-through.
- Keep one compact top summary per workspace; repeated KPI strips do not earn space.

### Batch B — campaign and monthly truth

- Link opening sales, closing buys, rolls, expirations, and assignments into campaigns.
- Preserve execution truth while showing cumulative campaign economics.
- Add a month-by-month ledger for option cash, dividends, total cash, fees, assignments, and covered capital.
- Add an expiration and committed-share calendar with earnings and dividend overlays when available.

### Batch C — honest strategy attribution

- Compare stock-only total return with actual stock-plus-options total return.
- Separate underlying movement, dividends, realized option cash, open option marks, fees, and capped upside.
- Show called-away economics and released capital without treating assignment as automatic failure.
- Add time-weighted and money-weighted returns only after external cash flows are represented correctly.

### Batch D — inspectable policy and research

- Implement per-name and per-tranche policy profiles.
- Record policy version and entry context on each new campaign.
- Study outcomes by DTE, strike buffer, delta, volatility regime, underlying, entry context, and disposition.
- Replace cross-strike average IV with repeatable standardized IV history when sufficient market data exists.

## Plain-language metric contract

- **Net option cash:** opening credits minus executed closing debits and fees for the selected period.
- **Dividends received:** cash dividends actually posted in the selected period.
- **Total strategy cash:** net option cash plus dividends received.
- **Estimated close value:** current market estimate for closing an open call; it is not a realized cost.
- **Open option gain/loss:** opening credit minus estimated close value; it remains unrealized while the call is open.
- **Model time decay/day:** theoretical one-day option-value change if other inputs do not change; it is not income.
- **Premium retained:** net completed option cash divided by gross opening premium, with the denominator visible.
- **Annualized option cash pace:** selected-period option cash divided by the stated covered-capital denominator and annualized; it is not total return.
- **Effective exit price:** strike plus net premium per share for an assigned or intentionally callable tranche, before tax.

Every derived value identifies its denominator and whether it is observed, derived, estimated, simulated, or unavailable.

## Work that can be completed before Schwab

- canonical campaign and monthly-ledger models;
- deterministic fixture scenarios and reconciliation tests;
- period-aware chart aggregation and daily drill-through;
- per-name/tranche policy configuration;
- expiration and obligation calendar UX;
- stock-only attribution calculations over fixture prices and transactions;
- quote-age, event, tax-context, and source-quality fields with honest unavailable states;
- compact and expanded contract-table behavior;
- persistent read, snooze, and acknowledgement behavior for alerts.

## Work that waits for verified live sources

- final Schwab transaction and assignment mappings;
- brokerage tax-lot delivery behavior;
- current NBBO, quote age, spread, Greeks, and contract IV;
- standardized historical IV, term structure, and skew;
- authoritative earnings, dividend, and corporate-action events;
- live slippage, execution-quality, and reconciliation statistics.

Missing live fields remain unavailable. Demo values never silently fill a live account.

## Implementation checkpoint

The verified pre-Schwab build now includes:

- a three-surface operator flow: Desk, Open Calls, and Results;
- exact 4W, QTR, YTD, and R365 cash windows derived from one execution ledger;
- a compact nonzero-event Desk tape, weekly quarterly comparison, monthly YTD/R365 comparison, and exact dated cash ledger in Records;
- the 700 CVX, 800 KTOS, and 500 URNM fictional inventory with personalized fictional call tranches;
- roll-linked campaigns, a month-by-month cash ledger, an expiration calendar, and current-inventory attribution;
- expandable open-call rows with obligation, quote, mark, liquidity, Greek, event, policy, and lifecycle fields;
- per-name and per-tranche retention policies without an unexplained trade score;
- persistent Nibwick read, snooze, and acknowledgement state in the local browser;
- deterministic reconciliation tests covering cash windows, campaign economics, obligations, attribution limits, and policy coverage.

Fixture attribution is deliberately labeled as a current-inventory proxy. Time-weighted and money-weighted returns, authoritative event overlays, verified NBBO and Greeks, historical IV research, tax-lot truth, and broker reconciliation stay deferred until the necessary live or imported source data exists.
