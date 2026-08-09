# Nibwick decision context

Nibwick's notes translate deterministic option-book calculations into plain English. Observed values, derived estimates, and heuristics stay visibly distinct. No note predicts assignment or recommends a trade.

## Fast move and roll review pressure

The closest open call receives a 0–100 review-pressure score. This is an attention-ranking tool, not a probability, risk limit, or roll signal.

- Strike proximity: 0–40 points, increasing linearly from 15% out of the money to 40 points at or through the strike.
- Positive five-session move: 0–30 points, increasing linearly and capped at a 25% move.
- Time urgency: 0–20 points, starting at 30 DTE and reaching 20 at expiration.
- Mark expansion: 0–10 points, starting when the current option mark exceeds entry credit and capped at 2× entry credit.
- Labels: `LOW` below 25, `MODERATE` from 25–49, `ELEVATED` from 50–74, and `HIGH` from 75.

The note also reports exact strike distance per share, strike distance percent, the same move across covered shares, current mark/entry credit, and DTE. It intentionally does not estimate the price or benefit of a roll because that requires a live replacement chain, bid/ask spreads, liquidity, user exit intent, taxes, and the new strike/expiry.

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
