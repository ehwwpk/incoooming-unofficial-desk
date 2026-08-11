# Incoooming capability roadmap

This map separates a professional analytics destination from what should be visible in the default workspace. It is intentionally broader than the first live Schwab release.

## Three-clock model

- **Cash clock:** executed credits, debits, dividends, fees, and realized lifecycle results.
- **Liability clock:** current option marks, Greeks, assignment exposure, catalysts, and scenarios.
- **Research clock:** volatility regime, execution quality, counterfactual stock-only return, and rule cohorts.

The product's advantage is joining these clocks while never collapsing them into one misleading “income” number.

## Present surface

The demo already proves the interaction and presentation model for:

- selectable rolling 4W, QTR, YTD, and rolling-365 cash windows, with daily source detail retained below the primary selector;
- net premium cash, dividends, total strategy cash, APR, rolling pace, and observed monthly distributions;
- active coverage, lifecycle counts, called-away shares, and lifetime income lens;
- daily underlying closes linked to simulated option and share events;
- per-call entry credit, current marked liability, open P/L, DTE, time value, theta, and strike distance;
- portfolio/name theta summaries and deterministic dividend/momentum desk notes;
- responsive chart/call layouts, adjustable full-screen split, focus ranges, and keyboard navigation.

These are not all live until broker transactions, market data, and lifecycle reconciliation populate the same typed dashboard contract.

## P0 — defend the ledger

Required before trusting live performance:

- immutable raw broker payloads with source and observed timestamps;
- normalized executions, fees, dividends, stock lots, option contracts, and lifecycle events;
- deterministic pairing of STO/BTC, expiration, exercise, assignment, and roll relationships;
- end-of-day position and cash reconciliation with explicit unresolved breaks;
- separate cash flow, realized P/L, and open marked P/L calculations;
- source drill-through from every total to executions and raw records;
- quote freshness and observed/derived/estimated status on market-dependent values.

## P1 — operate the open book

- per-contract bid, ask, spread, mark method, volume, open interest, and quote age;
- delta, gamma, theta, vega, intrinsic/time value, moneyness, and covered shares;
- called-away notional and concentration by name, expiry, sector, and catalyst;
- dividend and earnings overlap with early-assignment diagnostics;
- scenario grid for underlying moves, volatility shifts, time passage, and assignments;
- campaign economics for rolls: cumulative credit, debits, fees, time extended, strike movement, and open liability;
- explicit user intent by underlying or share tranche: preserve shares, neutral, acceptable exit, or intentional trim/redeployment;
- inspectable policy bands for DTE, strike buffer, coverage, catalysts, liquidity, and acceptable effective exit price.

## P1 — measure the strategy honestly

- stock-only baseline versus actual stock-plus-options result;
- capped-upside/opportunity-cost attribution after assignment or expiry above strike;
- time-weighted portfolio return and money-weighted personal return, net and gross of fees;
- buying-power/current-value/original-cost denominators shown separately;
- drawdown, downside capture, volatility, and return contribution by name;
- benchmark comparison against declared buy-write indexes where economically appropriate;
- tax-lot basis kept separate from the user's analytical income-adjusted basis.

## P2 — build the volatility research edge

- daily repeatable 30-day ATM IV snapshots rather than naive chain averages;
- IV rank/percentile, realized volatility, and forward IV-minus-subsequent-realized studies;
- term structure and fixed-delta call/put skew;
- entry and exit IV for every lifecycle;
- liquidity and slippage versus mid/NBBO at execution;
- cohort studies by DTE, delta, strike gap, IV regime, signal, underlying, and outcome;
- maximum favorable/adverse excursion, premium capture speed, and assignment/capped-upside effects;
- catalyst-aware studies that separate ordinary volatility from earnings or special events.

## P2 — professional workflow layer

- saved workspaces and user-selected columns/density;
- global command palette and keyboard-first drill-through;
- review queue driven by exceptions, with Nibwick as the optional human-language interface;
- table/export equivalents for every chart;
- annotations, decision journal, rule version, and post-trade review;
- configurable alert thresholds with visible method and snooze/read state;
- accessible contrast, focus, reflow, reduced motion, and text-size controls.

## Approval gates for major work

1. **Truth Engine:** transaction/lifecycle schema, reconciliation, and source drill-through.
2. **Open Risk Board:** contract grid, scenarios, catalysts, and portfolio exposure redesign.
3. **Volatility Lab:** snapshot collection, normalized IV history, skew/term structure, and cohorts.
4. **Attribution Lab:** stock-only baseline, capped upside, campaign economics, and professional returns.
5. **Workspace System:** customizable dense tables, saved layouts, accessibility controls, and exports.

The default desk should not display every capability. It should summarize exceptions and primary outcomes, then let the operator open the relevant specialized workspace.

The approved pre-live sequence, period simplification, plain-language metric contract, and personalized fixture direction are maintained in [the pre-Schwab operator plan](pre-schwab-operator-plan.md).

## Primary references

- OCC/OIC covered-call and assignment material: <https://www.optionseducation.org/strategies/all-strategies/covered-call-buy-write>
- OCC options disclosure document: <https://www.theocc.com/company-information/documents-and-archives/options-disclosure-document>
- Cboe buy-write benchmark methodologies: <https://www.cboe.com/us/indices/benchmark_indices/>
- Cboe volatility-analysis capability model: <https://www.cboe.com/solutions/portfolio-analytics/solutions/volatility-analysis/>
- Bloomberg Launchpad workspace model: <https://www.bloomberg.com.br/produto/launchpad/>
- WCAG 2.2: <https://www.w3.org/TR/WCAG22/>
