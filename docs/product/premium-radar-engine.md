# Premium Radar engine contract

## Purpose and boundary

The Radar engine converts an explicit symbol lookup, current market observations, account context,
and a versioned seller policy into an explainable research result. It does not recommend a security,
predict assignment, place an order, or modify the accounting ledger.

The same engine must work over Schwab, a future broker adapter, or an imported dataset. Every result
declares which facts were available, which were unavailable, and when they were observed.

## Input contract

Every run receives one immutable input bundle:

- owner, source, account or imported-dataset identity;
- canonical symbol and explicit mode: `covered_call` or `cash_secured_put`;
- underlying quote and daily bars, including observation times;
- call and put chain observations for the configured expiration range;
- current shares, already-covered lots, open short options, and explicitly reserved cash;
- a versioned global seller policy plus an optional symbol override;
- verified structured events and user-entered blackout dates;
- provider capability and freshness declarations.

Research observations are not ledger events. A lookup cannot create a position, cash entry, dividend,
assignment, or realized result.

## Symbol lookup rules

- Normalize whitespace and case before validation.
- Permit common listed-symbol punctuation through a provider-specific canonicalization adapter; do not
  interpolate raw input into a URL or query string.
- Verify that the provider recognizes the symbol and that an option chain exists.
- Never substitute a similar ticker silently.
- Never return random, trending, sponsored, or algorithmically discovered symbols.
- Held and saved symbols are shortcuts only. Choosing one is an explicit lookup.
- Keep one in-flight request per owner, source, account, symbol, and mode. A repeated request may reuse
  a fresh cached observation but must show its original observation time.

## Source and freshness states

Radar uses an explicit state machine:

- `idle`: no symbol has been submitted;
- `validating`: canonical symbol and provider support are being checked;
- `fetching`: quotes, bars, and chain observations are loading;
- `ready`: all required fields pass freshness and completeness gates;
- `partial`: useful results exist, but one or more optional capabilities are unavailable;
- `stale`: observations exist but exceed the configured age;
- `failed`: the provider request or normalization failed;
- `authorization_required`: the selected live source needs reconnection;
- `unsupported`: the symbol, option type, or required provider capability is unavailable.

Freshness limits are configuration, not hidden constants. Underlying quotes, option quotes, daily bars,
and events have separate limits. Market-hours and after-hours limits are separate. A result never
changes `stale` to `ready` merely because the market is closed.

## Seller policy

Global policy and symbol overrides record intent rather than forecast the market:

- allowed contract count and covered-share percentage;
- covered-call DTE bands, minimum strike, minimum strike distance, and call-away willingness;
- cash-secured-put DTE bands, maximum effective purchase price, reserved cash, and maximum
  post-assignment position weight;
- maximum bid/ask spread, minimum open interest, minimum volume, and quote-age limits;
- a 5% or higher simple annualized bid-based premium-rate floor;
- earnings, ex-dividend, macro, and manual blackout behavior;
- acceleration or gap rules that can make `WAIT` easier without pretending to predict direction.

For a cash-secured put, the user must enter an acceptable effective purchase price and reserve cash.
Margin buying power is not treated as reserved cash. For a covered call, the engine may use only
uncovered standard 100-share lots unless an adjusted deliverable is explicitly supported.

## Quote normalization

For a two-sided quote with positive bid and ask:

```text
midpoint = (bid + ask) / 2
spread_percent = (ask - bid) / midpoint * 100
```

Version 1 does not invent a fill estimator. It displays:

- `bid` as the conservative sell-side planning credit;
- `midpoint` as a market reference, never as promised execution;
- spread dollars and percent;
- bid/ask size when the provider supplies it;
- volume, open interest, and quote age.

Ranking uses the bid, not the midpoint. A later fill model may be added only after the user's own
limit-order and fill history can be measured and versioned. Zero-bid, crossed, locked, one-sided, or
stale quotes fail the execution gate or appear only as rejected evidence.

## Derived values

All calculations use decimal arithmetic, the normalized contract multiplier, and an explicit day-count
convention. Values that require unavailable inputs remain unavailable.

```text
call_room_dollars = strike - spot
call_room_percent = call_room_dollars / spot * 100

put_discount_dollars = spot - strike
put_effective_entry = strike - bid
put_cash_required = strike * multiplier * contracts

call_premium_yield = bid * multiplier / (spot * multiplier)
put_premium_yield = bid * multiplier / (strike * multiplier)
simple_annualized_rate = premium_yield * 365 / DTE
```

The interface labels these as simple annualized premium rates, not APR, forecast return, or portfolio
performance. The cash-security gate uses full strike cash and does not net the premium against the
required reserve.

Expected movement is a scale estimate, not a direction or assignment probability. Version 1 uses a
near-ATM implied-volatility estimate when a valid volatility observation exists:

```text
expected_move = spot * normalized_IV * sqrt(DTE / 365)
strike_distance_in_moves = absolute(strike - spot) / expected_move
```

The normalized IV unit and source are retained with the result. If a reliable near-ATM call and put
surface is unavailable, expected movement is `unavailable`; it is not reconstructed from a single
far-OTM contract. A later ATM-straddle estimate can be added as a separately named method.

IV rank and percentile require one independent daily sample per session, a declared lookback, and a
minimum sample count. Until then the output is `history building`. Intraday refreshes do not count as
new history days.

## Deterministic decision pipeline

1. **Eligibility**
   - valid standard contract and multiplier;
   - fresh underlying and chain;
   - uncovered share lots for calls or reserved strike cash for puts;
   - DTE, strike, effective-entry, position-size, and event-policy limits.
2. **Execution quality**
   - valid two-sided market and positive bid;
   - spread, quote-age, open-interest, volume, and size rules;
   - unavailable liquidity fields produce a visible capability warning, never a fabricated zero.
3. **Policy fit**
   - symbol-specific strike and DTE posture;
   - call-away willingness or acceptable put acquisition price;
   - coverage, cash, concentration, and expiration-crowding limits.
4. **Risk context**
   - expected-move distance, delta as sensitivity, realized and implied volatility context;
   - 5-, 20-, and 60-session movement, range position, gap state, and acceleration;
   - ex-dividend, earnings, official macro releases, and manual blackouts;
   - missing-data penalties and plain-language caveats.
5. **Diversified selection**
   - reject anything below the saved premium-rate floor before ranking;
   - partition the expirations actually returned into up to three contiguous near-to-far cohorts;
   - keep 5–60 DTE as a user-policy default, not a product capability ceiling;
   - retain no more than `MORE CREDIT`, `BALANCED`, and `MORE ROOM` in each cohort;
   - compare strike room in expected-move units when reliable IV is available;
   - return fewer than nine rows when the chain does not contain nine qualified choices.

The engine's top-level verdicts are `WAIT`, `REVIEW`, `DATA INCOMPLETE`, and `SOURCE STALE`. Candidate
labels describe trade-offs, not a recommendation. `WAIT` is a complete result and can be the only
result.

## Dominance and tie-breaking

For covered calls, candidate A dominates B only when A has no worse sell-side credit, no less strike
room, no longer duration, and no worse execution quality, with at least one strict improvement. For
cash-secured puts, replace strike room with no worse effective entry and post-assignment fit.

Stable tie-breakers are:

1. narrower spread percentage;
2. fresher quote;
3. higher open interest when available;
4. earlier expiration;
5. deterministic OCC-symbol order.

No opaque composite score is exposed as truth. Individual diagnostics may use bounded, versioned
scores only when every component and weight is inspectable.

## Explanation contract

Every admitted, rejected, or waiting result includes:

- observation time, source, parser version, and policy version;
- plain-English headline and at most three primary reasons;
- gate-by-gate status and the measured value versus the configured limit;
- missing capabilities and stale fields;
- the contract facts required to reproduce the calculations;
- a reminder that the output is planning context and not an order ticket.

Delta is always labelled as price sensitivity. American-style assignment is possible while a short
contract remains open. Covered-call dividend review uses moneyness, remaining extrinsic value, the
ex-dividend date, and the dividend amount when verified; it never outputs a precise assignment
probability.

## Required invariants

- Candidate call contracts never exceed currently uncovered standard lots.
- Candidate puts never exceed explicitly reserved strike cash.
- A symbol never crosses the user's minimum call strike or maximum effective put entry silently.
- A stale, zero-bid, sub-floor, or out-of-window contract cannot be a surfaced candidate.
- Missing events are `unknown`, not `none`.
- A broker capability gap cannot be presented as a zero value.
- Re-running the same immutable input and policy version produces the same output.
- A lookup cannot mutate cash, positions, realized income, dividends, assignments, or broker tokens.

## Evidence basis

OIC describes covered-call strike selection as a trade-off between premium and preserved upside and
notes that call-away should be acceptable to the writer. OIC defines a cash-secured put as a stock
acquisition strategy with cash set aside for assignment and an effective entry of strike less premium.
OIC also emphasizes bid/ask width and possible slippage. FINRA notes that American-style short options
may be assigned during the contract term and that account marks are not realized gains or losses. The
engine wording and gates preserve those distinctions.
