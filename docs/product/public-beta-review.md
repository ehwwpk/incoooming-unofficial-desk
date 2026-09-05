# Public beta review — September 4, 2026

The local project was reviewed for a GitHub beta release. The
review used the current local checkout, including its existing CSV-import changes, rather than
the older GitHub version. The follow-up sweep prepares all pending changes for a local commit;
these checks do not publish a GitHub release or social post.

## Changes made

- Results now exercises the production performance-comparison engine with 58 fictional valued
  sessions from May 15 through August 7, 2026. It shows Managed TWR, starting shares plus share
  trades, SPY price return, and SPY at starting stock exposure, with period selection, risk,
  capital, option economics, and visible methodology. The obsolete inventory-proxy fallback
  is hidden when this full comparison exists.
- The demo contains 18 short calls and two short puts. Put credits, liabilities, campaigns,
  calendar obligations, and roll-downs appear in the appropriate views. Full put strike
  collateral is $11,500 against $18,750 cash. Every historical fixture session also satisfies
  its share coverage and cash-security requirements.
- Risk Lens has all required modeled inputs across the mixed book. Its next-$1 figure explicitly
  refers to short-option sensitivity including gamma; stock-inclusive delta remains separate.
  Simulated inputs are labeled separately from input completeness.
- Demo cash, campaign links, share trades, monthly cash statistics, and ending inventory were
  reconciled across pages. The account's daily return comes from the same history as Results.
  External cash flows are removed from return calculations, with timing limitations disclosed.
- Radar uses the frozen demo clock and shares held quotes, replacement bids, and daily closes
  with the Desk and Roll Board. Every displayed roll candidate has a regression check for the
  same source ask, target bid, net cash, and timestamp on both screens. The handoff selector
  now retains the actual source contract.
- Selecting the demo isolates Radar's lookups and settings from the live book. Demo settings
  are held in memory and reset on restart. Dedicated demo mode does not initialize brokerage
  credentials. Browser sync requests from demo or CSV source selections are rejected.
- Windows CI now propagates native-command failures from the lint and JavaScript checks.
- The final sweep blocks CSV import and real-source selection in the standalone demo, with
  clear instructions to stop it and use the normal launcher. The welcome button opens the demo.
- CSV parsing now rejects IBKR rows with surplus cells that could shift monetary values,
  recognizes adjusted option roots in descriptions, and treats purchases of dividend or
  option-strategy funds as stock trades rather than dividends or option contracts.
- Generated demo quotes respect the price ordering of strikes within each expiration while
  preserving the exact quotes shared by the book and Roll Board.
- The README explains the app in everyday language and includes quick setup, a copyable agent
  prompt, and links to the new step-by-step demo/CSV guide. Schwab setup preserves an existing
  settings file, and launcher messages match the selected setup path and configured address.

## Validation

Validated on Windows with Python 3.12.14:

| Check | Result |
| --- | --- |
| Complete unit and integration suite | 755 passed |
| Python line coverage | 91.81% |
| Ruff | Passed |
| Strict mypy | Passed, 242 source files |
| JavaScript syntax | Passed for all application scripts |
| PowerShell launchers | All scripts parse successfully |
| Bandit | Passed with the project's existing B101/B105 exclusions |
| Dependency advisory audit | No known vulnerabilities found in the review runtime or the clean wheel environment after its pip upgrade, using pip-audit with OSV |
| Wheel build | Passed in an isolated build environment |
| Packaged application smoke test | Passed after installing the built wheel and its dependencies in a fresh Python virtual environment, with packaged migrations/assets and fresh SQLite data |
| Browser | Results chart and period selection, mixed option risk, put Roll Board, and put-to-Radar handoff inspected; no JavaScript errors observed |

An initial final-suite attempt encountered a Windows permission error in pytest's default temp
directory. The complete successful run used a fresh temporary directory inside the review
workspace. The installed Starlette/httpx test client emits a deprecation warning; it does not
affect these passing tests.

A bounded publication-hygiene scan inspected filenames across 93 local commits and searched
approximately 7.65 MB of textual additions for credential/key patterns and personal path/email
patterns. It found no matches in that scope. Local credential files, broker databases, and account
data were excluded from the review copy. This is a documented check, not a guarantee that every
possible secret representation has been detected.

## Remaining limits and release positioning

Present this as a local Windows beta. Current Schwab authorization, developer-app approval,
market-data entitlements, and a new live sync were not exercised during this review. The configured
Python 3.13/3.14 CI matrix still needs its GitHub run.

Demo stock history, option marks, Greeks, SPY path, and capital metrics are fictional. The history
contains an initial cash buffer, a $5,000 deposit, and a $50,000 withdrawal; the two flow-bearing
return links carry estimated timing and are excluded from daily risk. These fixtures demonstrate
accounting and presentation, not a backtest or the author's investment performance. Synthetic
Radar fallback chains, OHLC envelopes, and volume are illustrative. Connection-pending and live
refresh states were not exercised against a live account in this review.
