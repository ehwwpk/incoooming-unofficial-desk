# Incoooming Open Risk Board

## Job to be done

In Open Options, the Open Risk Board tells the Incoooming operator what can materially change before
the next review, why it matters, and which source data supports it. The Nibwick Roll Board is the
planning queue on that same surface. Both prioritize obligations and exceptions rather than
pretending to issue trade instructions.

## Default questions

- How many shares are obligated, at which strikes and expirations?
- Which names dominate called-away notional, delta, gamma, theta, or vega exposure?
- What is near a strike, expiry, dividend, earnings event, or liquidity failure?
- How fresh and complete are the positions, quotes, Greeks, and catalysts?
- Under transparent scenarios, what changes in option liability, stock value, and called-away state?

## Contract row

Each open option row has four compact groups:

1. Obligation: contracts, deliverable, covered shares, strike, expiration, DTE, account.
2. Market: underlying, bid/ask, spread, mark method, IV, delta, gamma, theta, vega, quote age.
3. Economics: entry credit, current liability, open marked P/L, intrinsic/time value, fees.
4. Context: user intent, dividend/earnings overlap, liquidity, campaign, and reconciliation status.

Advanced columns are opt-in. The default view must not repeat the same number in a card, row, and
chart unless each representation answers a different question.

## Portfolio exposure model

Aggregate contract Greeks use signed position quantity, contract multiplier, and the Greek's unit.
Dollar-delta, gamma-per-1-percent, theta-per-day, and vega-per-vol-point must name their units.

Required views:

- called-away notional and covered shares by name, account, expiry week, and sector;
- strike proximity buckets and expiration ladder;
- portfolio/name theta estimate, with quote timestamp and theoretical label;
- delta/gamma/vega concentration and missing-Greek coverage;
- uncovered, over-covered, adjusted-deliverable, and reconciliation exceptions.

## Scenario engine boundary

Scenarios are deterministic transformations, not forecasts. A scenario is identified by:

- valuation timestamp and source snapshot set;
- underlying move per name or portfolio shock;
- IV shift in volatility points;
- elapsed calendar/trading time;
- dividend/earnings assumption;
- pricing method and version.

Initial scenarios should show stock-value change, option-liability change, net covered-position
change, strike crossings, and assignments-at-expiry as separate outputs. A simple intrinsic-plus-
time-value approximation must be labeled as approximate; a later pricing model may replace it.

## Alert design

Alerts are derived exceptions with evidence and plain language:

- strike proximity changed materially;
- early-assignment context is elevated around ex-dividend;
- expiry concentration exceeds the user's threshold;
- spread/quote age makes the current mark unreliable;
- fast underlying move changes a previously comfortable call;
- scenario loss or called-away notional crosses a configured limit;
- source records or position replay disagree.

No alert can say "roll" or "buy back" as an instruction. It can say what moved, how close the
obligation is, what inputs drive the pressure, and what the operator may want to review.

## Status and confidence

Every risk value must expose observed-at time, quote quality, data completeness, calculation method,
and whether it is observed, derived, estimated, or simulated. Delta can be shown as a theoretical
ITM proxy only when explicitly labeled; it is not a guaranteed probability.

## Release slices

1. Open-contract read model from ledger plus latest market observations.
2. Portfolio exposure aggregation and expiration/concentration boards.
3. Catalyst overlaps and deterministic exception rules.
4. Versioned scenario engine with saved scenario presets.
5. Historical risk replay and pre/post-decision journal integration.

## Verification requirements

- Adjusted deliverables and non-100 multipliers produce correct obligation exposure.
- Missing Greeks reduce coverage percentages instead of becoming zeros.
- Stale or crossed quotes cannot silently drive a trusted mark.
- Portfolio aggregates equal the sum of visible contract contributions at the same snapshot.
- Scenario results are reproducible from stored inputs and method version.
- Keyboard, text zoom, table equivalents, and non-color status cues are tested.

## Primary references

- Schwab option Greeks: <https://www.schwab.com/options/options-greeks>
- Cboe RiskEdge features: <https://www.cboe.com/solutions/portfolio-analytics/solutions/risk-analysis/riskedge-features/>
- OIC bid/ask mechanics: <https://www.optionseducation.org/news/understanding-the-bid-and-ask-prices-for-options>
