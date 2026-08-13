# Premium Radar

## Product decision

Premium Radar is the forward-looking research workspace for covered calls and cash-secured puts.
It answers one question without turning the product into an order ticket:

> Given the shares or cash already in this account, what is worth reviewing now—and when is waiting
> the better answer?

It is the first item in the existing `Tools` menu, keeping Desk, Options, and Results reserved for
the user's live book. It is not a news feed, a generic option scanner, or an automatic recommendation
engine. Incoooming remains read-only.

The product contract is completed by two focused documents:

- [Premium Radar engine contract](premium-radar-engine.md)
- [Premium Radar implementation plan](premium-radar-implementation.md)

## Operator flow

The default view is deliberately quiet: one ticker field, a covered-call/cash-secured-put mode
control, and optional shortcuts for held or explicitly saved symbols. Visiting Radar never fetches
chains. A lookup starts only when the user submits a ticker or deliberately chooses a shortcut.

After a lookup, calls and puts are modes within the same symbol workspace so the underlying is never
duplicated across separate stock lists.

The loaded symbol shows:

- `WAIT`, `REVIEW`, or `RICH / HIGHER RISK`, with plain-language reasons;
- shares available in 100-share lots and, for puts, cash explicitly reserved by the user;
- quote and event-data freshness;
- zero to nine qualified comparisons across up to three adaptive near-to-far term cohorts, with no
  more than three IV-aware trade-offs per cohort and no forced filler;
- an expiration map joining recent daily closes to today's price, then showing each candidate's
  strike, expiration, in-the-money side, and expected-move reference without inventing a future
  stock-price path;
- the user's saved playbook for that symbol, not a universal magic threshold.

The map uses the same price scale for the stock and strikes. Selecting comparison `1`, `2`, or `3`
changes only the focused boundary and readout. For a call, the shaded side is above the strike; for a
put, it is below the strike. A put's effective entry after bid credit is separate because premium
changes the economics but not the assignment strike. Close strike labels receive display spacing and
remain connected to their exact level.

The expanded map may show optional `RSI 14` and `MACD 12/26/9` panes. Both are off by default and
use the same observed daily-close dates as the price chart. They never overlay the price/strike map,
change candidate filtering or ranking, or imply a future path. Warm-up periods are explicit: RSI is
unavailable before 15 closes, and the MACD signal/histogram is unavailable before 34 closes. The
price map visibly separates observed closes from the option-expiration horizon and labels real dates
across both regions.

Opening evidence reveals the chain slice, diagnostics, and alternatives. There is no default order
button. A candidate may be copied into a broker review checklist later, but the engine cannot place
or route a trade.

## Open-call roll review

Nibwick may deep-link one specific open covered call and one displayed later/higher replacement into
Radar. This is a narrow continuation of the note, not a recommendation and not an order ticket.

- the server revalidates the source call against the current normalized book;
- only the covered lots released by closing that source call are added to available comparison size;
- the requested replacement is admitted to the comparison set even when an ordinary new-sale rule
  rejects it, but every failed rule remains visible;
- the exact replacement is highlighted and selected; Radar never substitutes a nearby contract
  without the operator choosing it;
- the close leg uses the current chain ask when available and otherwise says that it is using the
  latest desk-snapshot ask;
- the replacement uses the refreshed sell-to-open bid;
- missing or stale legs produce an explicit unavailable or mixed-time state instead of reusing an
  earlier Nibwick quote.

The resulting debit or credit is planning math for the simultaneous two-leg spread described by
Schwab's roll workflow. It is not a fill estimate, probability, or instruction to roll.

## Two research universes

Radar must keep owned positions and possible additions visibly separate.

### Your book

This is the operating context for held shares and reserved cash. Held symbols may be shown as
shortcuts, but a chain is not loaded until the user chooses one. Radar can then evaluate:

- uncovered 100-share lots available for calls;
- existing call coverage, expiration concentration, and call-away posture;
- cash explicitly reserved for puts;
- the resulting portfolio after a possible assignment.

### Research shelf

A symbol search can add an unowned ticker to a private watchlist without polluting the live Desk.
The shelf is empty by default. Radar never invents, recommends, trends, sponsors, or automatically
adds an unowned ticker. It loads research only after the user types a symbol or deliberately opens a
previously saved symbol. The first gate for a cash-secured put is a user answer:
`I would accept owning this at $X`.

The shelf shows stock and option liquidity, effective put entry, resulting position size and sector
concentration, event dates, drawdown and gap history, and whether enough reliable data exists. High
premium alone cannot promote a stock. A ticker can remain `WATCH`, `RESEARCH INCOMPLETE`, or
`EXCLUDED` without producing a contract candidate.

The initial lookup path can use Schwab quote, price-history, and option-chain endpoints. Company
filing context can come from SEC EDGAR. Earnings dates, classifications, and richer fundamentals
must declare their own provider capability; Radar must not imply that the broker supplied facts it
did not provide.

## Seller playbooks

The engine should store reusable policies and allow symbol overrides. These describe intent rather
than predict the market.

- **Upside-protective growth:** prefer farther OTM strikes, preserve participation in explosive
  moves, commonly compare 2–5 week calls with a smaller 6–8 week farther-strike sleeve, and make
  `WAIT` easy when the stock is accelerating.
- **Flexible call-away income:** permit a limited number of closer, shorter calls when IV expands and
  the user is willing to recycle assigned capital; compare them with a farther-strike 6–8 week
  alternative.
- **Acquisition put:** only on a researched stock the user wants to own, using a maximum effective
  entry, cash budget, and resulting portfolio-weight limit.

Each symbol policy records allowed lots, DTE bands, minimum strike or effective entry, desired
coverage range, call-away willingness, event rules, and maximum post-assignment exposure. The
suggested strike is never allowed to cross a user floor silently.

## Portfolio and campaign context

A contract is not attractive in isolation. Candidate ranking also needs:

- current and post-assignment symbol, sector, and correlated-theme concentration;
- expiration crowding across the entire book;
- cash unlocked by a call assignment or consumed by a put assignment;
- selected-lot economic basis when available, with tax basis clearly separated;
- prior premium in the current campaign, without using past premium to disguise new downside risk;
- call-away total outcome at the strike and upside forgone above it;
- one- and two-expected-move stress views for the underlying—not just option P/L;
- comparison against leaving the shares uncovered, without presenting either path as a forecast.

For an open campaign, Radar should explain whether a new contract increases premium, extends time,
changes the strike, or stacks exposure on an already-crowded expiration.

## Candidate facts

Every candidate must earn its place with facts the seller can audit:

- strike, expiration, DTE, bid, ask, midpoint, and an estimated credit after configurable slippage;
- one-contract bid credit divided by calendar DTE as a plainly labeled planning pace; it is not
  theta, earned income, or a forecast of daily P/L;
- distance to strike in dollars and percent;
- strike distance in expected-move units;
- delta as a price-sensitivity measure—not an assignment probability;
- IV, IV history rank only after enough observations exist, and underlying realized volatility;
- spread as a percent of midpoint, displayed size when available, volume, open interest, and quote
  age;
- 5-, 20-, and 60-session return, range position, and recent gap or momentum state;
- premium divided by covered capital and a clearly labelled simple annualized rate, never a return
  forecast;
- covered-call call-away value and upside surrendered at the strike;
- cash-secured-put cash requirement, effective purchase price (`strike - premium`), and discount or
  premium to spot;
- earnings, ex-dividend, macro-release, and user-entered blackout dates that fall before expiration;
- the rule or preference that admitted or rejected the candidate.

American-style equity options can be assigned before expiration. The board must separately flag
early-assignment conditions such as an in-the-money call with little remaining extrinsic value near
an ex-dividend date. It must not present delta as the probability of assignment.

## Decision model

The engine is a sequence of explicit gates and diagnostics, not one opaque score.

1. **Eligibility** — available covered lots or reserved cash, supported option type, valid contract
   multiplier, fresh underlying price, and a complete chain observation. Missing lots or reserved
   cash prevents a row from being labelled ready, but does not erase an otherwise valid market
   comparison after the user explicitly requests that ticker.
2. **Execution quality** — maximum spread, minimum quote size when available, minimum open interest,
   and a visible low-liquidity exception rather than silent exclusion.
3. **Playbook fit** — per-symbol DTE bands, minimum strike distance, acceptable call-away posture,
   reserved cash, allowed lots, and event policy.
4. **Risk context** — expected-move distance, delta, momentum, realized volatility, IV context,
   dividend and earnings timing, and data completeness.
5. **Diversified selection** — reject contracts below the saved simple annualized premium-rate
   floor, then partition the listed expirations into up to three contiguous near-to-far cohorts.
   Within a cohort, retain up to three meaningfully different choices by balancing bid-based rate,
   strike distance in expected-move units, and execution quality; do not fill an empty slot with a
   weak contract. The default policy is 5–60 DTE, but it is not a product ceiling.

`WAIT` is a first-class result when no candidate clears the gates, quotes are stale, spreads are
poor, an event is too close, or premium does not compensate for the user's stated call-away posture.

The selection must preserve meaningfully different choices rather than mechanically return adjacent
strikes. A thin or low-premium chain can correctly return zero, one, or two rows in a cohort.

## Volatility and execution diagnostics

Current IV needs context, but no single volatility statistic is an edge claim.

- Compare contract IV with the underlying's stored IV history only after sufficient observations.
- Keep IV rank and IV percentile distinct and display the lookback and sample count.
- Compare implied with realized volatility over aligned horizons.
- Read strike skew and expiration term structure so an isolated earnings or macro expiration is not
  mistaken for a generally rich chain.
- Show bid/ask width as a percent of midpoint, size when available, volume, open interest, quote age,
  and whether the bid is zero.
- Estimate executable credit conservatively from the market, while keeping bid, midpoint, and the
  estimate visible. Do not rank on midpoint fantasy.

Expected move is a scale estimate, not a directional forecast or a guarantee. Delta remains a model
sensitivity. Assignment posture combines moneyness, DTE, extrinsic value, dividends, and the user's
willingness to transact; it is not relabeled as a precise probability.

## Outcome audit

Radar decisions should become an append-only research journal. For every surfaced or rejected
candidate, retain the inputs, policy version, quote time, reasons, and user action.

When enough history exists, replay only information known at that timestamp and measure:

- premium retained after close and roll debits;
- assignment frequency and the user's stated acceptance at entry;
- upside forgone after call-away;
- effective purchase price and subsequent drawdown after put assignment;
- adverse underlying movement and maximum capital committed;
- results by playbook, DTE band, strike-distance band, IV regime, event proximity, and liquidity;
- `WAIT` outcomes beside sold-contract outcomes.

This audit is for calibration, not a backtested promise. It must prevent look-ahead leakage and
survivorship-biased watchlists.

## Events without headline noise

Structured dates can change whether selling today is sensible, but headlines must not become a
pretend risk model.

- First release: ex-dividend dates already available from verified sources, earnings dates from a
  verified provider or manual entry, the official FOMC calendar, the official BLS release calendar,
  and user blackout dates.
- Later release: fresh SEC 8-K and filing arrival as context, not sentiment.
- Geopolitical or company news: an attributed, time-stamped context flag or user pause—not a numeric
  assignment probability and not a mechanical sell signal.

The board should lower its confidence when an important event source is missing. It must never
silently replace missing events with “none.”

## Data work required

The current Schwab market sync is optimized around open positions. Radar needs a separate,
rate-controlled candidate-chain collector for eligible held symbols, including names with no open
option. It should fetch only configured DTE bands and strike ranges, persist raw responses and
normalized snapshots, and expose observation time on every candidate.

IV history rank needs accumulated snapshots. Until the minimum history threshold is reached, show
the current IV and `history building`; do not manufacture a percentile.

The initial implementation should use real chain quotes and deterministic filters. Historical
decision audits and replay come only after enough snapshots have accumulated.

## Code boundaries

Keep the feature outside dashboard rendering code:

```text
application/opportunities/
  models.py
  candidate_universe.py
  chain_filters.py
  risk_features.py
  candidate_frontier.py
  event_context.py
application/ports/
  opportunity_market.py
application/workspaces/
  premium_radar.py
```

Broker adapters provide observations and declared capabilities. The opportunity application layer
owns policy, calculations, and explanations. Templates only render a completed projection.

## Delivery slices

1. Extend verified Schwab chain collection to held symbols and configured DTE windows.
2. Add per-symbol seller preferences and deterministic eligibility/execution gates.
3. Produce three explainable frontier candidates plus `WAIT` in a JSON projection and tests.
4. Build the compact Radar workspace with expandable chain evidence and clear freshness.
5. Add structured event sources and a manual blackout editor.
6. Add historical replay and decision audit only after sufficient live observations exist.

## Acceptance rules

- The unowned-ticker shelf is empty by default; only an explicit lookup or saved symbol can enter it.
- Radar never fills the shelf with trending, sponsored, random, or algorithmically discovered names.
- No candidate appears without source and observation time.
- A CSP may appear as `RESEARCH ONLY` before cash is reserved, but it cannot clear every rule or show
  ready size; margin buying power is never treated as cash security.
- A covered-call comparison may appear as `RESEARCH ONLY` without an uncovered lot, but ready size
  remains zero and shares committed to another short call are never counted as available.
- No “safe,” “guaranteed,” or unqualified “assignment probability” language.
- No simulated future stock path. Expected move is a labelled volatility scale, not a prediction.
- Every rejection and `WAIT` state has a plain-English reason.
- The same normalized engine can run over Schwab, an aggregator, or imported records while visibly
  degrading when a source lacks chain or event capabilities.

## Primary references

- [FINRA options overview](https://www.finra.org/investors/investing/investment-products/options)
- [OIC assignment FAQ](https://www.optionseducation.org/referencelibrary/faq/options-assignment)
- [OIC volatility and Greeks](https://www.optionseducation.org/advancedconcepts/volatility-the-greeks)
- [OIC bid and ask](https://www.optionseducation.org/news/understanding-the-bid-and-ask-prices-for-options)
- [OIC volatility rank, percentile, skew, and term structure](https://www.optionseducation.org/news/april-webinar-key-takeaways-understanding-volatility-and-options-skew)
- [OIC covered call](https://www.optionseducation.org/strategies/all-strategies/covered-call-buy-write)
- [OIC cash-secured put](https://www.optionseducation.org/strategies/all-strategies/cash-secured-put)
- [Cboe option-writing benchmarks](https://www.cboe.com/us/index_income/help/)
- [Cboe buy-write methodology](https://cdn.cboe.com/api/global/us_indices/governance/BXY_Methodology.pdf)
- [Federal Reserve FOMC calendar](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)
- [BLS release calendar](https://www.bls.gov/schedule/)
- [SEC EDGAR data APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
