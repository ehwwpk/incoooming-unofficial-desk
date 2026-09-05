# Three-minute public demo

Use `scripts/run-demo.cmd` from the latest local source. It runs on loopback with fictional data
and a separate demo ledger. Keep the SIM marker and August 7, 2026 date visible. Close any live
broker tabs before recording and frame the app rather than account settings or terminal history.

The point of the walkthrough is the context around premium cash: what remains open, what it costs
to close or roll, what stock risk remains, and whether the whole account has benefited. This is an
early self-hosted Windows beta for personal analysis. It has no order-placement workflow.

| Time | Show | Suggested narration |
| --- | --- | --- |
| 0:00–0:20 | Results, with the four benchmark lines visible | “I built Incoooming for my own covered-call and cash-secured-put tracking. Premium cash alone didn't answer the questions I cared about. This walkthrough uses fictional data.” |
| 0:20–0:55 | Inspect the chart, then select 1M and ALL | “This compares the managed account with the same starting shares plus share trades, SPY's price path, and SPY at the account's starting stock exposure. Identified deposits and withdrawals are removed from returns. Drawdown and the method notes help put that result in context.” |
| 0:55–1:20 | Desk: cash summary and 18 calls / 2 puts | “Opening credits, executed buybacks, and fees are kept separate from current option liabilities. Cash received is not completed profit. The open book includes calls and puts, with the obligation, expiration, and current mark alongside them.” |
| 1:20–1:55 | Options: Risk Lens, then URNM $55 put on the Roll Board | “Here I can compare current model sensitivities and inspect a put that's slightly in the money. Rolling down changes the possible purchase price and extends the obligation. The comparison uses the old contract's ask and the replacement's bid, so a larger premium doesn't automatically mean a better trade.” |
| 1:55–2:25 | Open a replacement in Radar; inspect its date, strike, cash, and filters | “Radar gives me a chain to research, including rejected candidates and the reasons. These are simulated quotes. The live connector uses Schwab data and exposes quote age and missing inputs.” |
| 2:25–2:45 | Results: option economics, then Method & Limits | “Completed campaigns, open mark P/L, and return comparisons answer different questions. The management difference is not isolated options alpha, and SPY here is price-only.” |
| 2:45–3:00 | Book gateway or repository README | “I'm open-sourcing this as a local Windows beta. You can try the demo without credentials, connect your own approved Schwab app, or import supported CSVs. I'd welcome reproducible issues and feedback.” |

Keep each view still for several seconds. At social-video size, readable figures matter more than
showing every drawer. A 1M return window is calendar-based; the Desk's 4W cash window is 28 days,
so their cash totals need not match. The visible ranges explain the difference.

## Exact interpretation

- All demo performance, quotes, and model inputs are fictional. None establishes trading skill,
  expected income, forecast returns, or a historical backtest. Do not describe demo returns as
  personal results.
- The starting-shares line includes discretionary share trades and excludes option activity and
  forced assignment deliveries. It is not a fixed buy-and-hold portfolio. The SPY exposure line
  matches starting stock value relative to net liquidation; it is not option-delta matched.
- Management difference is a percentage-point difference between return paths, not a standalone
  option profit or proof of alpha.
- Risk Lens's next-$1 figure concerns the short options, including gamma, with all underlyings
  moving together. The stock-inclusive exposure is shown separately. Theta is sensitivity to time,
  not a cash payment, and 100% model coverage means all required inputs exist, not model certainty.
- $11,500 is the two puts' full strike obligation. The demo has $18,750 cash, leaving $7,250 after
  that reserve. Its maintenance and buying-power figures are explicitly illustrative display
  assumptions, not Schwab margin rules or a promise of available trading capacity.
- A roll is a close plus a new opening. It can require a debit, commit more time or capital, and
  leave downside exposure. American-style options may be assigned before expiration; cash security
  funds the purchase obligation but does not protect the acquired shares from a fall in value.
  See the Options Industry Council's [assignment explanation](https://www.optionseducation.org/referencelibrary/faq/options-assignment)
  and [cash-secured-put description](https://www.optionseducation.org/strategies/all-strategies/cash-secured-put).
- Daily risk uses adjacent valued sessions. A return link with owner cash may carry an estimated
  timing label even when its endpoint values are complete. This is consistent with the importance
  of cash-flow timing in [time-weighted return methodology](https://www.gipsstandards.org/standards/gips-standards-for-firms/gips-standards-handbook-for-firms/);
  Incoooming makes no claim of GIPS compliance.

## Connection states

The standalone demo intentionally has no live sync. Show connection and refresh states only in a
separately prepared live segment, with financial identifiers obscured. The code review verifies
source selection and sync guards with temporary test databases; it does not certify a current
Schwab connection, developer-app approval, or quote entitlement.
