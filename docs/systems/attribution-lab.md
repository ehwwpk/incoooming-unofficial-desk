# Attribution Lab

## Job to be done

The Attribution Lab explains whether active premium management improved the actual portfolio result,
what it cost in capped upside and friction, and how that conclusion changes with the denominator and
time window. It does not grade assignments as failures by default.

## Required return identities

For a covered position, keep these components separate:

- underlying price return;
- dividends and other income;
- realized option P/L;
- change in open option liability;
- fees and execution friction;
- capped-upside/opportunity-cost effect;
- assignment/exercise cash and share effects;
- external deposits and withdrawals.

The actual total must reconcile to components. Cash collected is not itself profit, and a close
debit is not a loss until paired with its opening economics or classified in a lifecycle.

## Comparison baselines

### Stock-only counterfactual

Hold the shares that the actual strategy owned at the comparison start, apply real share trades and
external cash-flow rules explicitly, receive dividends, and omit the option overlay. Assumptions
about assigned shares must be visible: continue holding counterfactual shares, or stop at assignment.

### Declared covered-call benchmark

Compare only when the benchmark's overwrite cadence, moneyness, and underlying are economically
relevant. Cboe BXM/BXMD-style indexes are context, not proof that a custom multi-name book should
behave the same way.

### Cash/risk-free comparator

Use a named rate series and matching dates. "Beat 4%" must never be a hard-coded permanent truth.

## Return methods

- Time-weighted return measures investment performance while neutralizing external cash-flow timing.
- Money-weighted return measures the user's experience and is sensitive to contribution timing.
- Modified Dietz may provide an explainable interim estimate when exact daily valuations are absent.
- Net and gross of fees are distinct.
- Period return is primary; annualized pace is secondary and only shown when meaningful.

## Denominator discipline

APR/yield results must name their capital base:

- original tax-lot cost;
- current covered-share market value;
- strike/called-away notional;
- buying power or cash collateral;
- average capital employed during the period.

The product may show several denominators, but it must never call them all simply "APR."

## Campaign economics

A campaign groups related contracts without rewriting accounting truth. It shows opening credits,
closing debits, fees, cumulative net cash, realized option P/L, open liability, days extended,
strike changes, dividends, assignments, and released/redeployed capital.

Campaign relationships can be suggested deterministically, but an operator must confirm ambiguous
links. Original executions remain immutable.

## Capped-upside analysis

Opportunity cost is a counterfactual, not a cash debit. Required views:

- underlying value above strike while obligated;
- realized foregone upside after assignment under a stated horizon;
- premium/dividends retained versus stock-only baseline;
- downside cushion actually provided by net option economics;
- assignment exit price versus the operator's original intent and basis.

## Cohorts and review

Study outcomes by underlying, entry DTE, delta/moneyness, strike gap, IV regime, trend state,
catalyst overlap, disposition, and rule version. Sample size, median, distribution, and outliers are
more useful than one blended win rate.

## Release slices

1. Deterministic lifecycle pairing and period cash/realized/open reconciliation.
2. Stock-only baseline and option-overlay attribution.
3. Campaign relationships and roll economics.
4. TWR/MWR, drawdown, downside capture, and named benchmarks.
5. Cohort analysis, decision journal, and rule-version comparison.

## Verification requirements

- Component attribution sums exactly to the reported actual result.
- External cash flows affect MWR but are neutralized in TWR.
- Assignment tests preserve premium, share proceeds, basis, and counterfactual assumptions.
- Counterfactuals are reproducible and never overwrite actual records.
- Annualization is suppressed or warned for short/irregular windows.
- Tax-lot basis remains separate from the optional income-adjusted analytical basis.

## Primary references

- Cboe BXM benchmark methodology: <https://cdn.cboe.com/api/global/us_indices/governance/BXM_Methodology.pdf>
- Cboe BXMD benchmark methodology: <https://cdn.cboe.com/api/global/us_indices/governance/BXMD_Methodology.pdf>
- GIPS standards resources: <https://www.gipsstandards.org/>
