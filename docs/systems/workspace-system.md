# Incoooming Workspace System

## Job to be done

The Workspace System lets one Incoooming operator move from portfolio summary to name, contract,
calculation, and source evidence without losing context. It provides density and speed without
turning the desk into an unreadable wall of equally weighted boxes.

## Information architecture

Four primary surfaces share a consistent shell. Two maintenance identities stay off the rail:

- **Desk:** option income, dividends, observed pace, live covered-call inventory, and Nibwick exceptions.
- **Open Options:** short-call and short-put obligations, the Nibwick Roll Board, strike pressure, marks, and time decay.
- **Premium Radar:** book-first call or put research and roll-chain refresh. Visiting the tab does not fetch.
- **Results:** cash reconciliation, capture, lifecycle economics, outcomes, and basis.
- **Data Health** (`records`): executions, cash, positions, lifecycle events, source readiness, and provenance. Reached from BOOK and header sync, not a tab.
- **Volatility** (`volatility`): calculation identity only. The former lab page redirects to Radar. Pulse facts live on Radar idle chips and Open Options name headers.

The default Desk is an inverted pyramid: headline decisions first, supporting evidence second, raw
records last. Product tabs are the application hierarchy. Radar sits third because selling and rolling
are weekday work. Nibwick occupies the Desk's left corridor as an optional friendly exception
interface, not a parallel navigation system.

## Desk compression contract

The default Desk is optimized for a covered-call seller and dividend collector. Its first fold must
answer four questions without opening another panel:

1. What net option income and dividend cash did the selected window produce?
2. What is the normalized monthly pace, with no target gauge pressuring another trade?
3. How many calls and share lots are open, and which strike or expiration is nearest?
4. Is there a dividend overlap or Nibwick note worth reviewing?

The inventory uses one compact row per stock. Charts, event maps, individual contracts, Greeks, and
lifetime basis calculations remain available inside a single-stock disclosure, with only one stock
open at a time. The Desk may summarize specialist calculations, but their canonical detail lives in
Open Options, Results, Radar, or Data Health. This prevents repeated values from
competing with the two daily jobs: monitoring live obligations and measuring realized income.

## Layout model

Saved workspace state is presentation data, not financial truth. It can store:

- visible panels and order;
- split-pane proportions with bounded minimums;
- selected period, accounts, names, expiries, and filters;
- table columns, sort, grouping, density, and widths;
- chart range/focus preferences;
- reduced-motion, contrast, and text-density preferences.

Version each layout schema. Unknown or invalid settings fall back to a safe default without touching
financial records.

## Dense interaction principles

- Keyboard and pointer paths have equivalent capability.
- A global command palette finds symbols, contracts, workspaces, calculations, and source records.
- Sticky navigation reflects the section actually in view.
- Tables are the canonical high-density inspection surface; charts have matching tabular evidence.
- Progressive disclosure reveals detail on demand rather than duplicating every metric.
- Focus mode and zoom clarify dense charts without changing the underlying values.
- Resizing is bounded, reversible, and persisted only after the user completes the interaction.

## Accessibility and legibility

- Reflow works at 400% zoom without hiding actions or requiring two-dimensional scrolling for text.
- Focus is visible and not obscured by sticky headers or popovers.
- Color is never the only status or sign encoding.
- Motion honors `prefers-reduced-motion` and includes a still mascot state.
- Text and component spacing survive user overrides.
- Touch targets and keyboard focus targets are distinct where dense desktop tables require it.

## Notification model

Notifications are a queue with stable ids, unread/read state, evidence, target object, timestamp, and
severity. Opening and traversing the queue clears unread state according to an explicit policy.
Snooze/dismiss state is user workspace data; the underlying alert evidence remains reproducible.

## Export and portability

Every analytical table should export visible rows and a machine-readable full result with method,
timestamp, filters, and source ids. Saved layouts and alert preferences are portable separately from
broker credentials and financial data.

## Release slices

1. Typed workspace preferences and saved local layouts.
2. Shared data grid, command palette, filters, and cross-workspace deep links.
3. Calculation/source drill-through drawer and export contracts.
4. Accessibility control surface and automated reflow/focus tests.
5. Multi-user identity/authorization only if the product moves beyond local personal use.

## Verification requirements

- Invalid/old layout versions migrate or fall back safely.
- Fullscreen, half-screen, tablet-width, and 400% zoom layouts retain primary actions.
- Splitters are keyboard-operable and cannot collapse required information.
- Active navigation matches the destination after click and after manual scroll.
- Notification unread state behaves consistently after opening, traversing, snoozing, and refresh.
- Exports reproduce the visible calculation metadata and do not leak secrets.

## Primary references

- Bloomberg Launchpad workspace model: <https://www.bloomberg.com.br/produto/launchpad/>
- WCAG 2.2: <https://www.w3.org/TR/WCAG22/>
- UK Government dashboard testing guidance: <https://analysisfunction.civilservice.gov.uk/policy-store/data-visualisation-testing-dashboards-for-design-and-accessibility/>
