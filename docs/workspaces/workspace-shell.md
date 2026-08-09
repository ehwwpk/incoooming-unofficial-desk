# Workspace shell

## Decision

The Desk remains the fast portfolio overview. Four focused workspaces are independent routes and can be opened in the current browser surface or in explicitly requested named windows:

| Stable key | Current label | Route | Primary question |
| --- | --- | --- | --- |
| `desk` | Desk | `/` | What matters across the whole book right now? |
| `risk` | Open Book | `/workspaces/risk` | What do the open calls obligate and how are they marked? |
| `attribution` | Strategy Review | `/workspaces/attribution` | Where did results come from and is the pace repeatable? |
| `volatility` | Volatility Lab | `/workspaces/volatility` | How does observed movement compare with option pricing? |
| `records` | Source Ledger | `/workspaces/records` | Which records and sources support the displayed answer? |

Labels are catalog data. Keys are permanent identities used by routes, stored preferences, tests, and future layouts. Renaming a window must never require a data migration.

## Window behavior

- A normal link always navigates in the current window.
- `Open own window` is an explicit user action and reuses a stable named window.
- If a browser blocks the new window, navigation falls back to the current window.
- The app never creates windows during load.
- Same-origin windows share only account mask, selected symbol, and as-of context through `BroadcastChannel`, with `localStorage` as fallback.
- OAuth tokens, broker credentials, raw payloads, and account identifiers are not broadcast.

## Read-model boundary

Every workspace currently reads the same `DashboardSnapshot`. The Open Book and Volatility Lab add deterministic projections over that snapshot. When live data arrives, the route and template contracts remain unchanged; the live reader replaces the demo reader behind the existing application port.

## Accessibility and density

- The route remains usable when popups, JavaScript, or `BroadcastChannel` are unavailable.
- Navigation uses real anchors and a logical DOM/focus order.
- Dense tables scroll horizontally instead of compressing values into unreadable cells.
- Missing historical IV is labeled unavailable; it is not synthesized.
