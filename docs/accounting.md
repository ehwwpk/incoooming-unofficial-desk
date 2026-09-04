# Accounting and chart methods

This page defines the main financial labels in Incoooming. All calculations use normalized broker
records and decimal arithmetic. Missing values stay missing unless the interface identifies a
derived or estimated value.

## Option cash and profit

Net executed option cash for a period is:

```text
opening option credits - closing and roll debits - execution fees
```

This measures cash movement. It is not realized profit while a related short option remains open.
An opening credit can be offset by a later buyback, assignment economics, or a current open
liability.

Completed campaign P/L sums the executed cash for a linked, finished option campaign. Roll chains
keep the old-leg debit and new-leg credit as separate executions. Exercise and assignment remain
separate lifecycle events. The completed total stays blank when an opening, close, or lifecycle
event cannot be linked without an unresolved campaign.

Open option mark P/L is:

```text
opening credit allocated to the open position - latest option mark liability
```

It is an estimate at the latest stored mark, not an executed result or an order quote. The desk
shows the mark timestamp and prior-session status when available.

The option premium multiplier scales quoted option cash and Greeks. It is not treated as proof of
an adjusted contract's stock deliverable. When the source marks a contract adjusted but does not
provide its full OCC terms, share coverage, assignment notional, intrinsic value, and roll
comparisons stay unavailable while the broker-reported option value remains visible.

Schwab supplies one net amount for an entire trade. The normalized execution rows preserve that
transaction total, including the difference between the security-leg amounts and broker net cash.
For an all-option spread or roll, the option subtotal therefore reconciles to the broker
transaction. If one broker transaction mixes stock and option legs, Schwab does not provide a
reliable per-leg split for that transaction-level adjustment. The account cash total remains exact,
but the stock-versus-option attribution can differ by that adjustment. Check the source transaction
before treating that uncommon asset-level split as exact.

## Missing is not zero

An empty set can total zero. A set containing a position with a missing input cannot. Portfolio and
per-symbol open P/L, option liability, Greeks, theta, and covered-capital yield are therefore left
blank when any required component is unavailable. This prevents a partially quoted book from
looking safer or more profitable than it is.

A missing sale-day stock price is not replaced by the current price or by the first later close.
That event is omitted from the price chart, and its sale-price comparison is shown as unavailable in
the ledger. A roll comparison also requires executable sides of the spread: the existing short at
its ask and the replacement at its bid. A mark is not substituted for a missing buy-to-close ask.

Dividends, interest, financing costs, owner cash transfers, and security trades remain separate
from option cash. Deposits and withdrawals do not count as trading gains or losses.

## Account return

The managed Results line uses time-weighted account returns. When an interval has no usable
valuation around an owner deposit or withdrawal, its fallback return is:

```text
interval return = (ending net liquidation - external owner flow) / starting net liquidation - 1
```

When complete account valuations exist around an intraday owner flow, the interval is split at
those observations and the subperiod returns are geometrically linked. This reduces timing bias
instead of pretending the cash arrived at an endpoint. The resulting interval is labeled estimated
because the broker observations are not simultaneous with the transfer. A period that cannot
safely link the same account set is left unresolved rather than treated as a zero return.

The starting-shares comparison replays the opening stock portfolio with a fixed opening non-stock
cash residual. After inception, that residual changes only for owner flows, discretionary share
trades, share-adjusted dividends, and financing costs. Option activity and forced stock delivery
from assignment or exercise are excluded. Ambiguous forced-delivery matching excludes the affected
symbol-day instead of guessing. Lifecycle events retain source `stock_quantity`. When that field
is absent, delivery derived from the recorded contract multiplier remains decimal and is not
rounded to whole shares.

## Observed and reconstructed sessions

Schwab supplies a current account valuation when Incoooming syncs; it does not provide a complete
daily history of net liquidation. The chart therefore distinguishes four states:

- **Observed:** an adjacent pair of broker account valuations stored after the market close. Drawn
  as solid green.
- **Reconstructed or estimated:** a missing session valued from supported positions, cash activity,
  and available marks between two observed anchors. Drawn as dashed green and labeled in the chart
  details.
- **Endpoint bridge:** a flow-adjusted path between two observed endpoints when the stored data
  cannot support position replay. Drawn as thin dotted green and labeled estimated.
- **Unresolved:** insufficient or conflicting evidence. No managed value is plotted.

Reconstruction exists only between two observed account anchors with the same account coverage. It
uses stored daily closes, position snapshots, executions, cash movements, and option lifecycle
events. The final path is reconciled to the next observed account value. If position replay is not
safe, the fallback estimates the path between the two observed endpoints after removing owner-flow
effects. Accountless activity can be applied when the book has one brokerage account. With several
accounts, a gap containing accountless activity stays unresolved because the activity cannot be
allocated safely. Reconstructed values do not claim that Schwab supplied those missing closes.

SPY and leverage-matched reference paths are evaluated on the managed account's plotted sessions.
A short missing reference session between two real closes may carry the prior close and is labeled
estimated. A reference line never extends beyond its latest published close, and a long or
conflicting gap is left unavailable instead of being drawn as fresh market data.

Risk statistics use adjacent observed closes only. Reconstructed and multi-session intervals do not
enter daily volatility, positive-day rate, worst-day, or maximum-drawdown samples.

## Other labels

- **Option cash APR** annualizes net executed option cash over current stock market value. It is a
  cash-yield measure, not total return. It is unavailable when covered capital is incomplete.
- **Premium capture** is net executed option cash divided by opening credits for the selected
  window. It can be negative.
- **Cash-offset basis** subtracts tracked option cash and dividends from original purchase cost for
  an analytical capital-recovery view. It does not change broker or tax-lot cost basis.
- **Account day P/L** is the latest linked change in broker net liquidation after owner flows. It is
  unavailable when the account set changes or two usable session values do not exist.
- **Open-position day P/L** sums complete broker day prints for positions still open. It is a
  diagnostic and can differ from account day P/L because it excludes closed intraday positions and
  some cash items.

## Data checks

Raw source records remain immutable. Normalized executions, cash movements, lifecycle events, and
market observations retain source links. Full Schwab syncs are marked successful only after every
required ingestion stage completes. CSV imports require a preview; unsupported or uncertain rows
do not enter the ledger.

No performance method can repair incomplete or incorrect broker records. Compare results with the
broker statement and inspect Data Health when a number looks wrong.
