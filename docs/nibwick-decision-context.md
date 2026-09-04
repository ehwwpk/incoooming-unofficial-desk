# Incoooming Nibwick decision context

Nibwick is Incoooming's clerk. His notes translate deterministic option-book calculations into
plain English. Observed values, derived estimates, and heuristics stay visibly distinct. No note
predicts assignment or recommends a trade.

## Voice rules

Nibwick sounds like a sharp clerk who knows this particular book, not a generic assistant:

- Lead with the actual stock, contract, distance, or clock. Avoid vague narration such as “moved fast,” “needs context,” or “deserves review.”
- Address the operator directly with “you sold” and “your call” or “your put.”
- Use one brief human aside at most. Low-urgency notes can be dryly playful; assignment-sensitive and dividend-sensitive notes stay direct.
- End with what the fact means for attention, never a trade instruction. “Back on the desk” means inspect the position, not close or roll it.
- Keep model boundaries explicit. Nibwick can surface an open obligation; it cannot predict assignment or the next stock move.

## When notes are generated

Nibwick is evaluated whenever a dashboard snapshot is built. With the local server running, the Schwab source refreshes on its normal sync cadence and the page reloads after a successful sync; Nibwick then evaluates the newest normalized positions, quotes, price history, and dividend fields. It is not a separate cloud daemon and it does not run while the local app is shut down.

Review state is stored in the browser. Reviewing or snoozing a note changes its `new` state; it never removes an alert whose live condition still qualifies. The homepage therefore reports active notes separately from new notes, and the note panel keeps an always-visible symbol roster. A note becomes new again when the contract, severity, strike-proximity band, DTE band, or dividend event changes. This avoids both silent escalation and a duplicate alert every morning.

## Strike and expiration proximity

Open calls and short puts receive a low-noise proximity check:

- An in-the-money contract is surfaced within 30 DTE, with higher urgency inside 7 DTE.
- A contract within 3% of its strike is surfaced inside 21 DTE.
- A contract within 7% of its strike is surfaced inside 7 DTE.
- Every open short contract is checked before ranking. Only the highest-priority directional call note and highest-priority short-put note per symbol are shown, so one name cannot flood the desk. A dividend note may coexist because it represents a different event risk.

Short-put notes report strike distance, DTE, current mark versus entry credit, and assignment
notional (`known delivered shares × strike`). If stock delivery is not known, the notional stays
unavailable. Assignment notional does not claim that the trade is cash secured or describe broker
margin treatment.

## Fast move and roll review pressure

The closest open call receives a 0–100 review-pressure score. This is an attention-ranking tool, not a probability, risk limit, or roll signal.

- Strike proximity: 0–40 points, increasing linearly from 15% out of the money to 40 points at or through the strike.
- Positive five-session move: 0–30 points, increasing linearly and capped at a 25% move.
- Time urgency: 0–20 points, starting at 30 DTE and reaching 20 at expiration.
- Mark expansion: 0–10 points, starting when the current option mark exceeds entry credit and capped at 2× entry credit.
- Labels: `LOW` below 25, `MODERATE` from 25–49, `ELEVATED` from 50–74, and `HIGH` from 75.

The note also reports exact strike distance per share, strike distance percent, current mark/entry credit, DTE, and the 0–100 review-pressure label. Where later/higher live replacement quotes are available, the UI may show roll comparisons using the current buy-to-close ask and replacement sell-to-open bid. These are quote snapshots for planning, not a forecast, recommendation, or executable order. A same-strike later call is not a replacement: it does not restore share upside.

### From a note to Radar

A displayed roll comparison is one analysis action, not a generic Radar search. Choosing `CHECK FRESH CHAIN` carries only the verified open-call identifier and the displayed later/higher strike and expiration into Premium Radar. Radar then:

1. verifies that the source call is still open in the selected book;
2. releases only that call's known share delivery, in its brokerage account, for sizing the
   replacement;
3. requests a current chain wide enough to include the source expiration and exact replacement;
4. keeps the exact replacement visible even when it misses the operator's ordinary new-sale policy, while preserving its failed gates;
5. calculates buy-to-close ask minus sell-to-open bid and shows the quote timestamp;
6. highlights the requested replacement without selecting a different contract silently.

Radar treats this handoff as a nearby listed ladder, not an ordinary covered-call scan. It considers
only contracts with a later expiration and a **higher** strike for calls, or the same or a **lower**
strike for puts. Opening-sale filters such as DTE, APR, lots, and cash do not hide listed
replacements. The default display is the next three listed expiries and the next three listed
strikes in that direction, kept to about 8% of the source strike and 28 extra days, ordered by
expiry then strike. Same-strike date pushes are excluded for
calls because they do not restore share upside. One nearby row is marked nearest cash and time; an
exact Nibwick replacement outside that grid is appended when it remains eligible. Each row is
explicitly labeled `NEAR FLAT`, `NET CREDIT`, or `DEBIT FOR ROOM`. Ordinary Radar searches use a
separate reading order: nearest expiration first, then calls from lower to higher strike or puts
from higher to lower strike within that expiration.

The handoff has three visible outcomes: both legs refreshed, the replacement refreshed while the source ask remains the latest desk snapshot, or the exact replacement unavailable. An old Nibwick replacement quote is never reused as if it were current. A stale source call stops the comparison instead of opening an unconnected scan. Clearing the handoff returns Radar to an ordinary symbol lookup. Nothing in this path previews, places, replaces, or cancels an order.

## Dividend context

For calls that remain open across an ex-dividend date:

- Remaining time value per share is the call's current value minus intrinsic value, divided by covered shares.
- `dividend / time value` is displayed as a diagnostic ratio.
- Early-assignment sensitivity is elevated only when a call is in the money and the indicated dividend exceeds remaining time value.
- The pre-dividend gray line is `strike + indicated dividend`. It estimates the pre-dividend stock price needed to remain near the strike after a dividend-sized ex-date price adjustment. Market movement can overwhelm that adjustment, so the line is not a forecast or assignment boundary.

Regular dividends generally reduce the stock's quoted price on the ex-date, all else equal. The option holder, not the short-call writer, controls exercise, and there is no definitive way to know whether a specific short call will be assigned.

## Source basis

- [Options Industry Council: Options Exercise](https://www.optionseducation.org/referencelibrary/faq/options-exercise) explains that early exercise forfeits time value, assignment cannot be predicted definitively, and call exercise can increase near an ex-dividend date.
- [Cboe: Dividend Risk](https://www.cboe.com/insights/posts/dont-get-stuck-paying-the-dividend-on-your-short-trade/) describes the ITM plus dividend-greater-than-time-value combination and the expected ex-date price adjustment.
- [Charles Schwab: Ex-Dividend Dates and Dividend Risk](https://www.schwab.com/learn/story/ex-dividend-dates-understanding-dividend-risk) discusses extrinsic value versus the dividend and notes that the opening price can differ because of market forces.
- [Charles Schwab: Covered Calls Beyond the Basics](https://www.schwab.com/learn/story/covered-calls-beyond-basics) identifies strike distance, time, IV, delta, intrinsic/extrinsic value, and expiration proximity as relevant covered-call context.
- [FINRA: Understanding Assignment](https://www.finra.org/investors/insights/trading-options-understanding-assignment) states that short American-style equity options remain assignable while open and that assignment is uncertain.
- [OCC: Characteristics and Risks of Standardized Options](https://www.theocc.com/company-information/documents-and-archives/options-disclosure-document) is the controlling risk-disclosure reference.
