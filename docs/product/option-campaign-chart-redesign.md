# Option campaign chart redesign

## Decision

The next chart revision should stop making the operator decode a global event-number sequence. The
primary visual identity becomes the option **campaign**: one stable identity that survives an opening
sale, any later roll legs, and the final expiration, close, or assignment. Individual executions stay
auditable inside that campaign.

## Implementation status

The campaign renderer is now the only stock-chart renderer. The former feature flag and legacy
numbered ticket view were removed only after the live-ledger reconciliation gate passed.

The implemented slice provides stable call/put labels (`C1`, `P1`), quantity-aware partial-close
accounting, exact order-key roll links, explicit `UNKNOWN` links when identical open lots are
ambiguous, per-event campaign cash, campaign-colored paths, endpoint labels, campaign focus, a
campaign index, and one net share marker per symbol/day. Raw broker rows remain immutable.

The renderer does not guess through corrections or cancellations. Ambiguous identical lots remain
visible with inferred or unknown confidence, and the campaign audit reports every exclusion. The
legacy fallback was removed only after representative live-history reconciliation proved campaign
cash and remaining quantities against the atomic execution ledger.

## Why the current chart eventually breaks

The current renderer already provides daily closes, range controls, same-day vertical offsets,
sale-to-resolution links, click details, and a written event tape. Its weak point is identity:

- visible numbers are assigned again from chronological display order, so `#8` has no durable meaning;
- `lifecycle_id` is derived from a sale event's temporary sequence rather than a persistent campaign;
- templates receive `campaign_id`, but the visual grammar does not expose or depend on it;
- live linking uses last-in-first-out matching by option symbol, which can mis-stitch partial closes
  or overlapping identical contracts;
- a roll is detected as two executions sharing an order key, but the replacement does not remain
  visually attached to the prior campaign across later rolls;
- collision offsets consider only events on the same date, not markers that overlap across nearby
  dates and prices;
- five fixed vertical lanes repeat after the fifth collision;
- color, event number, event glyph, outline, and connector currently compete for attention.

Changing the palette before repairing identity would make a prettier ambiguity.

## Visual grammar

### Stable campaign tag

Assign each normalized campaign a short, stable display tag per underlying: `C1`, `C2`, `C3`. The
tag is created from persistent campaign identity, never the current chart range or sort order. A tag
does not change when the user switches 16W to 8W or when older history enters the window.

The calm view labels the campaign's first visible node and latest unresolved node. Intermediate legs
use compact status glyphs in the same visual family. This avoids repeating `C2` over every leg while
keeping the path identifiable without a hover ritual.

### Campaign color plus event shape

Use an accessible, dark-terminal palette of at most four simultaneously emphasized campaign hues.
Reuse may occur only when campaign paths cannot overlap in the visible window. Color is never the
only carrier of meaning:

| Event | Shape/fill | Meaning |
| --- | --- | --- |
| Sell to open | filled square | premium entered the campaign |
| Buy to close | hollow square with end cap | that contract was closed |
| Roll close/open pair | coupled square nodes with one elbow/curve | old leg closed and new leg opened |
| Expired | ring with center dot or `X` notch | obligation ended worthless |
| Assigned/called | clipped corner plus assignment notch | shares changed because of assignment |
| Share buy/sell | small neutral circle in the inventory lane | underlying inventory changed |

Open campaigns retain full saturation. Resolved campaigns recede to roughly 45% visual emphasis until
focused. Assignment keeps a restrained red edge but retains campaign hue, because red describes the
resolution rather than inventing a new campaign.

### Direct labels, not a decoding wall

Active campaigns get a direct short label near their latest node: `C2 - $75C - SEP 18`. Resolved
campaigns default to tag plus shape. A compact key explains shapes once; campaign colors do not need
a legend because the label sits on the path. This follows the principle that a legend should not make
the reader repeatedly associate remote colors with data.

## Path and collision behavior

1. Anchor every node to the exact execution date and observed underlying price with a fine stem.
2. Route the campaign path through a deterministic lane above or below the price trace; never draw a
   connector through its own label.
3. Pack nearby nodes using rectangle collision tests across both date and price, not date alone.
4. Prefer the prior lane for the same campaign so a roll path reads as one continuous object.
5. Fan same-session roll pairs by a few pixels and bind them with one elbow or shallow curve.
6. Group very dense executions behind one campaign node with a visible count; clicking expands the
   members. Do not shrink text until it is unreadable.
7. Aggregate share executions into one **net inventory marker per symbol per day**, preserving gross
   buys, gross sells, weighted prices, and net shares in details. If the day nets to zero, keep the
   auditable event in the inventory rail but do not compete with the price trace.
8. Re-run packing after 16W/8W/4W changes; stable campaign tags and colors do not change.
9. Request and render markers only for the visible range. Dense off-screen history belongs in the
   campaign index, not the SVG.

### Two visual lanes, not one pile

Premium campaign events stay anchored to the price trace. Ordinary share buys and sells move to a
quiet inventory rail directly below the plot and are hidden by default when the chart enters a dense
state. A small `SHARES` control reveals them without altering the option campaign paths. Assignment is
the exception: it remains on the campaign path because it resolves the option and changes inventory.

The inventory rail uses a neutral `+SH` or `-SH` pill, never another global number. Selecting it opens
the day's net shares plus the underlying executions. This preserves the stock story without letting
routine accumulation drown the option strategy.

## Interaction model

The calm default answers only: what campaigns are open, how they got here, and how they ended.

- Hover or keyboard focus gives one-line facts without moving the chart.
- Click locks **campaign focus**: unrelated paths dim, the entire sale-to-roll-to-resolution path
  brightens, and the existing anchored detail panel shows every leg in chronological order.
- The detail panel reports separate executed cash facts and campaign totals: premiums received,
  close/roll debits, current open value, net realized cash, total campaign credit, current strike and
  expiration, and stock price at each leg.
- Clicking a roll node focuses both legs and labels the net roll debit/credit. It never collapses two
  legally and economically separate executions into one accounting row.
- Escape, background click, or a visible close control returns to the calm view.
- Range changes preserve focus if the campaign remains visible; otherwise focus clears with a short
  status announcement.
- `SHARES` toggles the inventory rail. `LABELS` can reduce non-focused campaign labels to shapes, but
  never hides the latest unresolved obligation.
- A collision cluster shows one campaign tag plus a count. Keyboard focus or click expands it in a
  local popover; merely moving the pointer is never required to recover the facts.

The ledger below the chart becomes a campaign index, not a duplicate event list. Each row starts with
`C#`, current/final status, total campaign cash, and the most recent contract. Opening it reveals the
auditable legs.

## Data invariants before implementation

The first engineering phase is a normalization audit, not CSS.

1. A campaign has a persistent identifier independent of chart sequence and viewport.
2. Every execution leg has a broker/source execution identifier and normalized option identity.
3. A roll stores both source and replacement execution IDs plus the compound order ID when provided.
4. Partial closes and partial rolls split quantities explicitly; no last-in-first-out guess may consume
   more contracts than a source leg has open.
5. Same-day close and reopen is not called a roll unless source data or deterministic matching proves
   the association.
6. Expiration and assignment resolve remaining quantity, not merely the latest matching symbol row.
7. Corrections and cancellations supersede prior events without silently rewriting history.
8. Symbol changes, splits, non-100 multipliers, adjusted options, and multiple accounts remain distinct.
9. `campaign_id` and `parent_record_id` flow from normalization into `PriceEvent`; display code never
   manufactures lineage from chronological sequence.
10. Campaign cash totals reconcile exactly to the underlying execution rows.

When source data cannot prove a link, show separate events with `LINK UNKNOWN`; do not draw a confident
campaign path.

## Performance and accessibility budgets

- Default emphasis is capped to open campaigns plus the focused resolved campaign.
- DOM marker count is bounded by visible range; off-range details remain in the data model, not the DOM.
- Marker hit targets remain keyboard accessible even when glyphs are visually compact.
- Hue, fill, shape, and line texture provide redundant identification.
- Text and critical boundaries retain at least 3:1 non-text contrast against the plot; focused controls
  meet the product's normal text contrast target.
- Reduced-motion mode disables path drawing and marker transitions without hiding state.
- Large books collapse dense history by campaign before they sacrifice legibility.
- Campaign identity, status shape, and accessible text remain meaningful in monochrome; hue is an
  accelerator, not the database key painted on screen.

## Hostile cases to prototype

- two campaigns with the same strike and expiration opened on the same day;
- one four-contract call partially closed, then two contracts rolled and two later assigned;
- three consecutive rolls crossing monthly and quarterly reporting windows;
- two roll orders on the same date at nearby underlying prices;
- a source correction that changes quantity or execution time;
- expiration recorded without an underlying close on the calendar date;
- an adjusted option with a non-100 multiplier;
- a called-away share event and an ordinary share sale on the same day;
- 30+ campaigns in 16 weeks with focus, half-screen, keyboard, and reduced-motion checks.
- 20+ visible raw executions that collapse into three campaign paths and four net daily share events;
- one day containing a share buy, a partial close, and a roll pair at nearly the same price;
- a dense chart with `SHARES` off, then on, proving that hiding the rail never hides assignment.

## Delivery sequence and gate

1. **Done:** quantity-aware campaign reconciliation and hostile fixture tests.
2. **Done:** campaign paths, endpoint labels, campaign focus, share toggle, and campaign index.
3. **Done:** reconciled the current Schwab ledger into 29 short-premium campaigns: 25 exact, four
   quantity-aware inferred, zero unknown, with one long-option lifecycle event excluded.
4. **Done:** hostile fixtures cover partial closes, partial assignment, overlapping identical
   contracts, long-option exclusion, and non-100 multipliers.
5. **Done:** removed the legacy numbered renderer after the reconciliation gate passed.
6. **Still an explicit coverage gap:** the current live ledger contains no observed adjusted-contract
   event. The multiplier-aware path is tested, but a real OCC-adjusted contract has not yet been
   reconciled from this account and must not be described as live-proven.

## Research basis

- TradingView execution marks attach actions to exact bars, group dense executions, and can omit labels
  for a calmer view.
- TradingView marks support multiple interactive marks on one bar; trading primitives distinguish
  order, position, and execution objects with configurable lines and shapes.
- Carbon recommends direct labels where possible and redundant texture/color encoding.
- Option sellers repeatedly describe the need to keep each roll leg auditable while also seeing the
  cumulative campaign credit, break-even, and final outcome.
- DefiLlama's strongest transferable pattern is metric-first progressive disclosure: a small default
  surface with deeper custom views, not every metric on one plot.

## Locked recommendation for the next implementation turn

Do not replace `1, 2, 3 ... 20` with a prettier set of global numbers. Replace the global sequence with
persistent `C1`, `C2`, `C3` campaign identity, action-specific shapes, and a separate inventory rail.
The first implementation slice should be data-only: persist and test campaign lineage, partial
quantities, roll pairs, and unresolved links. Only then prototype the new renderer behind a feature
flag beside the current chart. That order prevents the interface from confidently drawing a campaign
the ledger cannot actually prove.
