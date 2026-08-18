# Incoooming workspace shell

## Decision

The Desk remains Incoooming's primary daily operating surface. Nibwick patrols the left corridor.
Open Options, Premium Radar, and Results sit beside it in the product nav, in that order.
Data Health remains an independent maintenance route from BOOK and header sync. Volatility keeps its
workspace key; `/workspaces/volatility` redirects to Radar. Workspaces can open in the
current browser surface or in explicitly requested named windows:

| Stable key | Current label | Route | Primary question |
| --- | --- | --- | --- |
| `desk` | Desk | `/` | What matters across the whole book right now? |
| `risk` | Open Options | `/workspaces/risk` | Which shorts deserve a look, and what nearby listed rolls can be compared? |
| `attribution` | Results | `/workspaces/attribution` | Where did results come from and is the pace repeatable? |
| `radar` | Premium Radar | `/workspaces/radar` | Given this ticker and these seller rules, what is worth reviewing? |
| `volatility` | Volatility Lab | `/workspaces/volatility` | Redirects to Radar. Realized-vol pulse lives on Radar idle and Open Options. |
| `records` | Data Health | `/workspaces/records` | Which records and sources support the displayed answer? |

Labels are catalog data. Keys are permanent identities used by routes, stored preferences, tests, and future layouts. Renaming a window must never require a data migration.

The Desk itself is intentionally shallow: one income panel, one live-call panel, one compact row per
stock, a weekly income history, and a closed audit trail. Opening a stock reveals its full chart and
contract book; opening Radar reveals on-demand chain research. This is
progressive disclosure, not a second tab hierarchy.

Open Options uses nested disclosure without hiding the portfolio pulse. The Nibwick Roll Board is
the first specialist surface: nearby listed replacements with two-leg planning math, never an order
ticket. Its four summary numbers distinguish option lines from contract quantity. `Next expirations`
starts open because time is the daily operating constraint; the contract register remains folded
until needed. The browser remembers the operator's disclosure choices. Individual calls then open
for exact DTE, time used, option value versus premium, quote, Greeks, value mix, and liquidity.
Short puts appear in the same obligation book instead of creating a disconnected stock row. Native
`details` and `summary` elements preserve keyboard operation when JavaScript is unavailable.

## Window behavior

- A normal link always navigates in the current window.
- `Open own window` is an explicit user action and reuses a stable named window.
- If a browser blocks the new window, navigation falls back to the current window.
- The app never creates windows during load.
- Same-origin windows share only account mask, selected symbol, and as-of context through `BroadcastChannel`, with `localStorage` as fallback.
- OAuth tokens, broker credentials, raw payloads, and account identifiers are not broadcast.

## Read-model boundary

Every workspace reads the same `DashboardSnapshot`. Open Options adds deterministic
projections over that snapshot. Radar idle reuses stored realized-vol pulse facts without fetching.
The live Schwab reader and isolated demo reader sit behind the same
application port, so route and template contracts do not depend on the source.

## Accessibility and density

- The route remains usable when popups, JavaScript, or `BroadcastChannel` are unavailable.
- Each workspace provides a breadcrumb, a clear return to the Desk, and an optional own-window action without duplicating a directory.
- Dense tables scroll horizontally instead of compressing values into unreadable cells.
- Missing historical IV is labeled unavailable; it is not synthesized.
