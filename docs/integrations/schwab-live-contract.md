# Verified Schwab live contract

This adapter contract was verified against the approved Trader API and Market Data API on
August 10, 2026. The verification inspected field names, categorical values, signs, counts, and
cross-ledger totals without printing credentials, account identifiers, symbols, or financial
amounts.

## Read-only endpoints

- Trader API account numbers and accounts with positions;
- Trader API transactions in non-overlapping 59-day windows over a rolling year;
- Market Data quotes for held underlyings;
- Market Data option chains bounded to the expirations of open short calls;
- Market Data one-year daily price history for covered-call underlyings.

The clients expose GET operations only. There is no order-entry, replacement, cancellation, or
preview method in the adapter.

## Refresh contract

The live local server schedules a full read-only refresh after startup and every 15 minutes by
default. Manual CLI and browser refreshes use the same coordinator and cannot overlap an active
run. A full refresh is considered current only after accounts/positions, transaction history, and
market observations all finish; failed full runs are persisted separately from the last successful
snapshot and surfaced as an attention state. Closing the local server stops the schedule.

## Observed transaction contract

Transactions expose an activity identity, source timestamps, transaction type, signed net cash,
and transfer items. Security transfer items expose signed quantity, signed cost, price,
position effect, and instrument identity. Option instruments expose put/call, strike, expiration,
underlying, multiplier, and OCC-compatible symbols.

Normalization rules:

- negative option quantity plus `OPENING` is a sell-to-open;
- positive option quantity plus `CLOSING` is a buy-to-close;
- transaction net cash is retained as the executed cash truth;
- security cost is retained as gross execution cash and the difference to net cash is recorded as
  fees;
- `DIVIDEND_OR_INTEREST` remains split between dividend and interest using the source description;
- `RECEIVE_AND_DELIVER` remains a lifecycle record and is classified as assignment, expiration,
  exercise, or adjustment from the broker description;
- SMA adjustments are not treated as cash income;
- transfers and journals never become strategy income.

## Observed market contract

Underlying quotes expose bid, ask, last, mark, prior close, and exchange quote time. Option-chain
contracts expose bid/ask/mark, implied volatility, delta, gamma, theta, vega, rho, volume, open
interest, multiplier, strike, expiry, and source quote time. Daily history exposes real OHLCV
candles.

Exchange timestamps and retrieval timestamps remain separate. Repeated after-hours quotes with an
unchanged exchange timestamp are versioned by retrieval event; the latest projection returns one
row per instrument. Historical candle revisions are append-only and the read projection selects
the newest observed version for each symbol/date.

## Reconciliation gates

The live implementation independently re-sums the newest raw transaction page set and compares it
with normalized records. The following must all match before the dashboard is trusted:

- covered-call execution count;
- net option cash;
- gross opening/closing cash;
- dividend cash;
- assignment/expiration/exercise lifecycle count;
- open-position/chain quote coverage;
- one latest candle per symbol and market date.

Roll pairing, per-symbol dividend attribution when Schwab supplies only a currency transfer, and
chart lifecycle reconstruction remain derived projections. They must not rewrite the immutable raw
or normalized ledger.
