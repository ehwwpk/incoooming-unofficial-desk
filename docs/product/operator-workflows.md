# Premium operator workflows

The desk is designed around recurring decisions, not around every field a broker can expose. Dense data belongs on screen only when it changes the next review, explains an outcome, or proves the ledger.

## 1. Open the desk

Answer in under ten seconds:

- What needs attention before the next market close?
- Which calls are closest to their strikes, expiration, or an ex-dividend date?
- How much of the book is covered, and how concentrated is called-away exposure?
- Is any quote, position, transaction, or dividend record stale or unreconciled?

Nibwick owns exceptions. The main desk owns portfolio state. Alerts remain closed until requested and never pretend to be trade instructions.

## 2. Decide whether to sell premium

The decision workspace should eventually combine:

- uncovered share capacity and user-defined assignment willingness;
- the underlying and share-tranche intent: preserve shares, neutral, acceptable exit, or intentional trim/redeployment;
- underlying trend, drawdown, realized volatility, and scheduled catalysts;
- repeatable 30-day at-the-money IV, IV percentile, term structure, and call skew;
- candidate strike distance, delta, credit, DTE, liquidity, and annualized cash yield;
- the user's historical outcome for comparable entries.

No single score should hide these inputs. A ranking may direct attention, but its method and components must remain inspectable. The same strike or DTE can be acceptable for a deliberate CVX trim and unacceptable for an upside-preservation KTOS tranche.

## 3. Monitor open calls

Every contract row needs four distinct lenses:

1. Obligation: quantity, strike, expiry, DTE, coverage, and assignment exposure.
2. Market: underlying price, distance to strike, bid/ask, mark, IV, delta, gamma, theta, and vega.
3. Economics: entry credit, current liability, open marked P/L, remaining time value, and fees.
4. Context: dividend/earnings overlap, liquidity, lifecycle/campaign link, and the user's intended disposition.

The default row is compact. Detailed Greeks, scenarios, and source records belong behind focus or expansion controls.

## 4. Manage a lifecycle

A roll is two executions and one optional campaign relationship. The system must preserve both truths:

- accounting truth: close debit and new opening credit are separate cash events;
- strategy truth: related contracts can be studied as one campaign with cumulative net credit, time extended, strike changed, and realized/open economics.

Assignment is an expected covered-call outcome, not automatically a failure. The lifecycle view should show share proceeds, option result, foregone upside after the call-away point, dividends retained or lost, and the next use of released capital.

## 5. Close a month, quarter, or year

The review sequence is:

- reconcile source transactions and positions;
- separate premium received, executed close debits, realized option P/L, and open marked P/L;
- add dividends and fees without relabeling them as option P/L;
- attribute stock movement, option overlay, capped upside, and assignment effects;
- compare actual period return with a stock-only baseline and a declared covered-call benchmark;
- study outcomes by underlying, entry rule, DTE, delta, IV regime, and lifecycle disposition.

Daily cash records remain available inside every period. They represent executions, fees, and dividends on the dates they occur; model theta per day remains a separate open-liability estimate and never fills days without cash events.

## Presentation rules

- Portfolio first, underlying second, contract third, source record last.
- Exceptions interrupt; ordinary state does not.
- Actual period return precedes annualized pace.
- Cash, realized, marked, estimated, simulated, and benchmark values never share an unlabeled total.
- Color is redundant with text, glyph, or sign.
- Charts expose a matching event tape or table.
- Keyboard navigation, visible focus, zoom/reflow, and reduced motion are product requirements.
