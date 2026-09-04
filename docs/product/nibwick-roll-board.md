# Incoooming Nibwick Roll Board

## Job

The Roll Board is Incoooming's book-wide review queue inside **Open Options**. It answers one
question before the operator opens a ticker: which short option obligations deserve a look now, and
what replacement contracts can be compared with auditable two-leg cash math?

It supports short calls and short puts. It is planning context, never an order ticket or instruction
to roll.

## Review zones

- **Needs attention:** in the money with 30 or fewer days remaining.
- **Worth checking:** within 3% of the strike with 21 or fewer days remaining.
- **Keep an eye on this:** within 7% with seven or fewer days remaining.

The board sorts by urgency, expiration, absolute strike distance, symbol, and strike. Assignment
notional uses a known stock deliverable rather than assuming every option controls 100 shares. It
stays unavailable for adjusted contracts whose full OCC deliverable is not in the source data.

Nibwick's posture summarizes the board:

- `PATROL`: no open short option is in a review zone;
- `WATCHING`: one or more contracts merit a look;
- `AT THE DESK`: at least one contract needs attention;
- `DATA FOG`: a contract merits review, but the loaded quotes cannot support honest roll math.

## Roll math

The source contract is priced at its buy-to-close ask. Every replacement is priced at its
sell-to-open bid. Fees are excluded and the UI says so. Calls must move to a later expiration
and a strictly higher strike; a same-strike date push does not restore share upside and is
not mixed into the default frontier. Puts may move to the same or a lower strike in a later
expiration. A casual call roll-down or put roll-up is also excluded.

The selector returns the nearby listed ladder: the next three listed expiries and the next three
listed strikes in the protective direction, limited to about 8% of the source strike and 28 extra
days, capped at nine. It does not fill leftover slots with far-dated or far-strike contracts.
Among those nearby quotes, one row is marked **Nearest cash and time**: first
by cost band ($0.10 / $0.25 / $0.50), then fewer extra days, then smaller absolute cash, then a
credit over a debit. Theta is displayed as model context when present; it never filters the ladder.
A requested Radar target that is eligible but outside the 3×3 grid is appended. If that target is
already an open short, the row is labeled `ALSO OPEN`.

Candidates may be a net credit, near flat, or a debit paid for more strike room. The board does not
mix adjusted and standard contracts in one cash comparison. It also explains when the chain has no
directionally valid contract, later expiration, positive replacement bid, or trustworthy source ask.

## Shared engine

Nibwick alerts, the portfolio Roll Board, and Premium Radar call the same pure selector. A Nibwick
handoff includes the source contract and selected target; Radar refreshes the chain and recomputes
the BTC-ask/STO-bid comparison rather than trusting stale display math.

Every reviewed contract has one stable browser anchor. Nibwick can open that exact Roll Board row;
the Board carries the same anchor into Radar; and Radar can return to the originating contract. The
trail changes navigation only. It does not preserve or imply an executable quote.

## Verification boundary

The verification boundary is the stored chain already loaded for those short-option underlyings,
not only the open contracts themselves. “No clean roll” means none was found in that loaded range
under these rules; it does not prove that no listed alternative exists. Quote age, spread, open
interest, and volume remain visible context, not a promise of execution quality.
