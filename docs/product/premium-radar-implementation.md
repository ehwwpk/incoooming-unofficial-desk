# Incoooming Premium Radar implementation

Status: the idle workspace, explicit lookup, comparison drawers, and Roll Board handoff ship in
Incoooming. Remaining slices are structured event calendars, IV-history rank, and decision replay.
Keep this file as the Radar placement and adapter contract.

## Placement and first impression

Radar uses `/workspaces/radar` and appears first in Incoooming's `Tools` menu. It does not add another
top-level navigation system. Desk remains the default operating view.

The unopened workspace is a purposeful empty state:

1. `PREMIUM RADAR` heading and one sentence of plain-English scope;
2. one labelled ticker field with a clear button;
3. a two-state mode control: `Covered call` or `Cash-secured put`;
4. `LOOK UP` as the sole primary action;
5. compact `FROM YOUR BOOK` and `SAVED` shortcuts, which trigger the same explicit lookup;
6. one useful empty-state note: Radar does not place trades and may conclude that waiting is better.

No candidate grid, decorative market feed, chart, or auto-loaded chain appears before lookup. Search
supports Enter, Escape, visible focus, and a WAI-ARIA combobox only if real symbol suggestions are
implemented. Dynamic lookup status uses a non-disruptive status region.

## Loaded workspace

The symbol workspace follows the existing Bloomberg-dense shell while preserving Apple-like hierarchy:

- **Context tape:** symbol, spot, quote age, selected source/account, owned shares, uncovered lots or
  reserved cash, and last completed market session.
- **Decision line:** verdict plus a short explanation; source and freshness states remain visible.
- **Trade-off table:** at most three candidate rows with strike, expiration/DTE, bid, midpoint, room or
  effective entry, expected-move distance, delta, spread, open interest, and simple annualized premium.
- **Evidence drawer:** rejected contracts, gate measurements, volatility context, events, and formulas.
- **Policy drawer:** task-specific symbol controls beside the result they affect.
- **Expiration map:** recent daily closes end at a labelled `TODAY` hinge. Forward space contains
  candidate strike lanes, expiration endpoints, the selected contract's ITM side, and one explicitly
  non-predictive expected-move reference. It does not duplicate the Desk's historical campaign chart
  or draw a theoretical future stock path.

Compact comparison cards are the primary fact surface. Each shares a visible number with the map;
selecting it persists a subtle highlight and changes the focused boundary without navigating away.
Unavailable values use `--` plus a nearby reason; they never display as `$0` or `0%`.

## Lookup request lifecycle

Page rendering never calls a broker. The browser starts a lookup explicitly:

```text
POST /api/v1/radar/lookups
{
  "symbol": "KTOS",
  "mode": "covered_call",
  "source_context_id": "..."
}
```

The response returns a lookup identifier, normalized symbol, and state. The client then reads:

```text
GET /api/v1/radar/lookups/{lookup_id}
```

Short requests may complete immediately; longer requests use bounded polling with backoff. There is
no endless spinner. The browser can cancel display polling without cancelling persistence of an
already-received market observation.

Related endpoints remain narrow:

```text
GET /api/v1/radar/policies/{symbol}?mode=...
PUT /api/v1/radar/policies/{symbol}
GET /api/v1/radar/symbols?scope=book|saved
POST /api/v1/radar/saved-symbols
DELETE /api/v1/radar/saved-symbols/{symbol}
```

There are no create-order, preview-order, replace-order, or cancel-order routes.

## Application boundaries

```text
domain/opportunity.py

application/opportunities/
  models.py                 # immutable inputs, results, reasons, and capability states
  symbol_policy.py          # global policy plus symbol override resolution
  quote_math.py             # spreads, yields, expected movement, and decimal rules
  eligibility.py            # share, cash, contract, DTE, strike, and event gates
  execution_quality.py      # quote and liquidity gates
  risk_context.py           # volatility, momentum, concentration, and event facts
  frontier.py               # dominance, labels, and deterministic tie-breaking
  explain.py                # plain-English reasons from structured outcomes
  expiration_map.py         # deterministic price/time coordinates and collision-safe labels

application/ports/
  opportunity_market.py     # source-agnostic quotes, bars, chains, and capabilities
  opportunity_store.py      # policies, saved symbols, runs, candidates, and events

application/services/
  run_premium_radar.py      # orchestration only
  read_premium_radar.py     # projection only

application/workspaces/
  premium_radar.py          # workspace projection composition

infrastructure/schwab/
  opportunity_gateway.py    # rate-controlled CALL/PUT/ALL lookup adapter

infrastructure/database/
  opportunity_reader.py
  repositories/opportunity.py

api/routes/
  radar.py

web/templates/workspaces/
  _premium_radar.html

web/static/
  premium-radar.css
  premium-radar.js
  premium-radar-map.js
```

Files may be split further when a module has more than one reason to change. Dashboard routes,
templates, the cash ledger, and the current open-position sync do not absorb Radar logic.

## Schwab adapter now in place

Account sync stores dense nearby chains for held short-option underlyings, mapping both
`callExpDateMap` and `putExpDateMap`. Radar still uses a separate lookup adapter so an explicit
ticker, including a name with no open option, cannot delay the regular account refresh. That adapter:

- requests `CALL`, `PUT`, or `ALL` as required;
- maps both call and put expiration maps with the correct option side;
- accepts bounded DTE and strike-count parameters;
- supports explicitly entered or held symbols even when no option is open;
- retains raw payloads and normalized observations with request and observation times;
- declares missing size, Greeks, events, or history instead of synthesizing them;
- uses per-source rate limiting, a short market-hours cache, and one in-flight lookup per key;
- cannot delay or fail the regular account-and-position refresh.

The existing read-only OAuth client remains the credential boundary. Radar adds no trading scope.

## Persistence

Use focused tables with migrations rather than JSON hidden in workspace preferences:

- `radar_policies`: owner, source/account scope, symbol, mode, typed policy values, version, timestamps;
- `radar_saved_symbols`: explicit user saves only, with source scope and timestamps;
- `radar_lookup_runs`: request identity, symbol, mode, state, source times, policy version, capability
  snapshot, parser version, and failure reason;
- `radar_candidate_snapshots`: run, instrument, normalized facts, gate outcomes, frontier label, and
  explanation data;
- `radar_manual_events`: user blackouts with date, scope, note, and provenance.

Raw broker chain payloads continue through the existing raw-market-event store. Normalized option
observations can extend the current market tables, but Radar reads them through a dedicated port.
Lookup rows are append-only except for bounded state transitions during one run. Policy changes create
a new policy version.

## Projection contract

The template receives a completed `PremiumRadarProjection`; it performs no financial math. The
projection includes:

- lookup state, canonical symbol, mode, source identity, source capability, and freshness;
- context tape values;
- verdict and ordered structured reasons;
- zero to three frontier rows;
- rejected evidence grouped by gate;
- policy form values and validation messages;
- explicit unavailable-field reasons;
- chart context only when requested.

Workspace routing must build only the projection for the requested workspace. It must not build Desk,
Options, Results, Volatility, Data Health, and Radar projections on every request.

## Failure and recovery behavior

- **Authorization required:** keep the last saved result visible and marked stale; offer `Reconnect
  Schwab` without deleting the lookup history.
- **Rate limited:** retain the current result, show the retry time, and do not hammer the provider.
- **Partial chain:** show source facts and rejected evidence, but do not promote incomplete contracts.
- **Unknown event capability:** say `Event data unavailable`, never `No events`.
- **Unsupported symbol:** keep the typed ticker in the field and explain the provider response.
- **Network failure:** preserve the previous timestamped result; allow an explicit retry.
- **Imported source without live chains:** explain that Radar cannot produce live candidates from that
  source unless a compatible market-data capability is selected later.

## Verification matrix

### Unit tests

- symbol normalization and rejection of unsafe input;
- decimal midpoint, spread, premium-rate, cash-requirement, and expected-movement calculations;
- covered-lot and reserved-cash readiness, including zero-size research comparisons;
- DTE, strike, effective-entry, concentration, quote-age, liquidity, and event gates;
- missing-capability and stale-state propagation;
- dominance, representative labels, stable tie-breaking, and `WAIT`;
- explanations generated from structured reasons, not free-form financial logic.

### Property and invariant tests

- call contracts never exceed uncovered standard lots;
- puts never exceed reserved strike cash;
- policy floors are never crossed silently;
- stale, crossed, one-sided, or zero-bid quotes never reach the frontier;
- dominated candidates never survive frontier selection;
- identical immutable inputs and policy versions produce identical results;
- a lookup cannot change ledger balances, positions, income, dividends, assignments, or credentials.

### Adapter and integration tests

- real-shape Schwab fixtures containing both `callExpDateMap` and `putExpDateMap`;
- CALL, PUT, and ALL request parameters and bounded DTE windows;
- raw payload retention, option-side mapping, idempotency, parser versions, and quote times;
- cache reuse, in-flight deduplication, rate-limit recovery, token refresh, partial payloads, and errors;
- route behavior proving that page GET performs no broker lookup;
- explicit lookup, policy update, saved symbol, and stale-result recovery paths.

### Rendering and accessibility tests

- idle, loading, ready, wait, partial, stale, authorization, unsupported, and failed states;
- keyboard submission, Escape, visible focus, status announcements, disclosure semantics, and reduced
  motion;
- table readability at wide, half-screen, and mobile widths;
- map label spacing, selected-card linkage, call/put ITM direction, keyboard selection, and the rule
  that historical price points never extend beyond the evaluation date;
- empty, missing, long-symbol, long-reason, and large-number layouts;
- no `$0` substitution for unavailable values and no hidden horizontal clipping.

### Live verification

Use explicit CVX, KTOS, and URNM lookups. For each, manually compare the underlying, several strikes,
expirations, bid/ask values, Greeks, and timestamps against the source response. Confirm policy behavior
matches the user's different call-away posture by symbol. Place no orders.

## Delivery sequence

Present in Incoooming: slices 1–5, plus Roll Board handoff onto the nearby listed ladder.

Remaining:

6. Add verified structured events and manual blackouts.
7. Accumulate one sample per session before enabling IV history context.
8. Add append-only decision audit and replay only after enough live observations exist.

The original build order for the shipping slices:

1. Add option-side-complete normalization and tests without changing current sync behavior.
2. Add the opportunity ports, Schwab lookup adapter, cache, and raw-observation persistence.
3. Add versioned policies, deterministic gates, calculations, frontier selection, and JSON projection.
4. Add the idle Radar workspace and explicit lookup lifecycle under `Tools`.
5. Add loaded comparison, evidence, and policy drawers with accessibility and responsive QA.

## Definition of ready

Those original gates were met before Radar shipped. Remaining work does not reopen the CALL-only
adapter gap or the first-in-Tools placement decision.
