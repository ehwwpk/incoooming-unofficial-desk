# Incoooming Volatility Lab

Status: calculation module. The former Volatility Lab page is no longer a destination;
`/workspaces/volatility` redirects to Radar. Realized-vol and range-position pulse facts from stored
closes appear on Radar idle chips and Open Options name headers. Rebuild a lab only after end-of-day
ATM snapshots exist. Keep `application/volatility` and the `volatility` workspace key.

## Job to be done

Incoooming's Volatility Lab tests whether the operator is being paid enough for the volatility and
path risk sold, using repeatable historical observations rather than visually attractive but
incomparable IV snapshots.

## Observation contract

Store point-in-time chain/quote observations with source, timestamp, bid, ask, mark method,
underlying price, option identity, IV, Greeks, volume, open interest, and quote quality. Preserve
missingness and never mix observations from incompatible timestamps without labeling the join.

## Normalized volatility series

Raw contract IV is not a stable time series because strikes and expirations change. Build normalized
series using documented interpolation rules:

- fixed horizon, initially 30 calendar days;
- fixed moneyness or delta, initially ATM and selected call deltas;
- term interpolation between surrounding expirations;
- strike/delta interpolation within an expiration;
- minimum liquidity and quote-quality requirements;
- method version retained with each derived point.

If the surface is too sparse, return unavailable with a reason. Do not fill it with a chain average.

## Core research views

- ATM IV history, rank, and percentile over a stated lookback;
- realized volatility at multiple backward-looking horizons;
- forward study: entry IV versus subsequently realized volatility;
- term structure by tenor;
- call/put skew at fixed deltas;
- IV and spread change from entry to current/exit;
- event/catalyst segmentation;
- liquidity and execution price versus bid/ask/mid.

IV rank and percentile must show their lookback, observation count, and sampling policy. Realized
volatility must show return definition, annualization convention, and trading-calendar source.

## Strategy cohorts

Join volatility context to lifecycles by the exact entry timestamp or a documented nearest snapshot.
Analyze premium capture, realized P/L, capped upside, maximum adverse/favorable excursion, assignment,
and holding duration by:

- entry IV percentile and IV-minus-realized spread;
- DTE and delta/moneyness;
- term structure and skew state;
- trend/drawdown regime;
- spread/liquidity quality;
- earnings/dividend/event proximity;
- underlying and user rule version.

The lab reports distributions and sample sizes. It does not optimize rules on tiny samples without a
visible overfitting warning.

## Data frequency and retention

For personal use, a practical first collector stores one end-of-day normalized snapshot plus
event-time observations around executions. Intraday chain collection is optional and must have an
explicit retention policy because it grows quickly.

Derived normalized points can be rebuilt from raw observations when method versions change.

## Release slices

1. Exact option/underlying observation store with quote-quality metadata.
2. Repeatable 30-day ATM and fixed-delta series.
3. Realized volatility, IV rank/percentile, term structure, and skew.
4. Execution-context joins and forward IV-versus-realized studies.
5. Cohorts, excursion analytics, and research notebook/export interfaces.

## Verification requirements

- Same input surface and method version produce the same normalized point.
- Sparse, stale, crossed, or one-sided markets fail transparently.
- Calendar/trading-day conventions are covered by boundary tests.
- Rank/percentile behavior is tested for ties, short histories, and missing sessions.
- Entry joins cannot use a market observation from after the execution without an explicit policy.
- No binary floats enter persisted financial calculations.

## Primary references

- Cboe VolEdge volatility analysis: <https://www.cboe.com/solutions/portfolio-analytics/solutions/volatility-analysis/>
- Cboe Mosaic visualization: <https://www.cboe.com/solutions/portfolio-analytics/solutions/visualization>
- Cboe options analytics: <https://www.cboe.com/solutions/options-analytics/global-options-analytics>
