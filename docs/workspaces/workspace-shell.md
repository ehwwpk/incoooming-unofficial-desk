# Workspace shell

## Decision

The Desk remains the primary daily operating surface. Its F1-F4 rail navigates Desk sections only. Four secondary tools remain independent routes, reached through one global `TOOLS` disclosure, and can open in the current browser surface or in explicitly requested named windows:

| Stable key | Current label | Route | Primary question |
| --- | --- | --- | --- |
| `desk` | Desk | `/` | What matters across the whole book right now? |
| `risk` | Open Calls | `/workspaces/risk` | What do the open calls obligate and how are they marked? |
| `attribution` | Strategy Review | `/workspaces/attribution` | Where did results come from and is the pace repeatable? |
| `volatility` | Volatility Lab | `/workspaces/volatility` | How does observed movement compare with option pricing? |
| `records` | Data & Records | `/workspaces/records` | Which records and sources support the displayed answer? |

Labels are catalog data. Keys are permanent identities used by routes, stored preferences, tests, and future layouts. Renaming a window must never require a data migration.

## Window behavior

- A normal link always navigates in the current window.
- `Open own window` is an explicit user action and reuses a stable named window.
- If a browser blocks the new window, navigation falls back to the current window.
- The app never creates windows during load.
- Same-origin windows share only account mask, selected symbol, and as-of context through `BroadcastChannel`, with `localStorage` as fallback.
- OAuth tokens, broker credentials, raw payloads, and account identifiers are not broadcast.

## Read-model boundary

Every tool currently reads the same `DashboardSnapshot`. Open Calls and Volatility Lab add deterministic projections over that snapshot. When live data arrives, the route and template contracts remain unchanged; the live reader replaces the demo reader behind the existing application port.

## Accessibility and density

- The route remains usable when popups, JavaScript, or `BroadcastChannel` are unavailable.
- The `TOOLS` control uses the disclosure-navigation pattern: real links, `aria-expanded`, Escape-to-close, outside-focus dismissal, and a logical focus order.
- Each tool provides a breadcrumb, a clear return to the Desk, and an optional own-window action without duplicating a permanent tab bar or directory.
- Dense tables scroll horizontally instead of compressing values into unreadable cells.
- Missing historical IV is labeled unavailable; it is not synthesized.
