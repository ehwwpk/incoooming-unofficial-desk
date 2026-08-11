# Workspace shell

## Decision

The Desk remains the primary daily operating surface. Its F1-F4 rail navigates Desk sections only. Four secondary tools remain independent routes, reached through one global `TOOLS` disclosure, and can open in the current browser surface or in explicitly requested named windows:

| Stable key | Current label | Route | Primary question |
| --- | --- | --- | --- |
| `desk` | Desk | `/` | What matters across the whole book right now? |
| `risk` | Open Calls | `/workspaces/risk` | What do the open calls obligate and how are they marked? |
| `attribution` | Results | `/workspaces/attribution` | Where did results come from and is the pace repeatable? |
| `volatility` | Volatility Lab | `/workspaces/volatility` | How does observed movement compare with option pricing? |
| `records` | Data Health | `/workspaces/records` | Which records and sources support the displayed answer? |

Labels are catalog data. Keys are permanent identities used by routes, stored preferences, tests, and future layouts. Renaming a window must never require a data migration.

The Desk itself is intentionally shallow: one income panel, one live-call panel, one compact row per
stock, a weekly income history, and a closed audit trail. Opening a stock reveals its full chart and
contract book; opening a secondary tool reveals portfolio-wide specialist analysis. This is
progressive disclosure, not a second tab hierarchy.

Open Calls uses nested disclosure without hiding the portfolio pulse. Its four summary numbers remain
visible. `Next expirations` and `Open calls` start folded and open when their full headers are clicked;
individual contracts then open for exact DTE, time used, option value versus premium, quote, Greeks,
value mix, and liquidity. Native `details` and `summary` elements preserve keyboard operation when
JavaScript is unavailable.

## Window behavior

- A normal link always navigates in the current window.
- `Open own window` is an explicit user action and reuses a stable named window.
- If a browser blocks the new window, navigation falls back to the current window.
- The app never creates windows during load.
- Same-origin windows share only account mask, selected symbol, and as-of context through `BroadcastChannel`, with `localStorage` as fallback.
- OAuth tokens, broker credentials, raw payloads, and account identifiers are not broadcast.

## Read-model boundary

Every tool reads the same `DashboardSnapshot`. Open Calls and Volatility Lab add deterministic
projections over that snapshot. The live Schwab reader and isolated demo reader sit behind the same
application port, so route and template contracts do not depend on the source.

## Accessibility and density

- The route remains usable when popups, JavaScript, or `BroadcastChannel` are unavailable.
- The `TOOLS` control uses the disclosure-navigation pattern: real links, `aria-expanded`, Escape-to-close, outside-focus dismissal, and a logical focus order.
- Each tool provides a breadcrumb, a clear return to the Desk, and an optional own-window action without duplicating a permanent tab bar or directory.
- Dense tables scroll horizontally instead of compressing values into unreadable cells.
- Missing historical IV is labeled unavailable; it is not synthesized.
