# Nibwick Roll Board

## Job

The Roll Board is the book-wide review queue inside **Open Options**. It answers one question before
the operator opens a ticker: which short option obligations deserve a look now, and what replacement
contracts can be compared with auditable two-leg cash math?

It supports short calls and short puts. It is planning context, never an order ticket or instruction
to roll.

## Review zones

- **Needs attention:** in the money with 30 or fewer days remaining.
- **Worth checking:** within 3% of the strike with 21 or fewer days remaining.
- **Keep an eye on this:** within 7% with seven or fewer days remaining.

The board sorts by urgency, expiration, absolute strike distance, symbol, and strike. Assignment
notional uses the contract's actual multiplier rather than assuming every option controls 100 shares.

Nibwick's posture summarizes the board:

- `PATROL`: no open short option is in a review zone;
- `WATCHING`: one or more contracts merit a look;
- `AT THE DESK`: at least one contract needs attention;
- `DATA FOG`: a contract merits review, but the loaded quotes cannot support honest roll math.

## Roll math

The source contract is priced at its buy-to-close ask. Every replacement is priced at its
sell-to-open bid. Fees are excluded and the UI says so. Calls may move to the same or a higher strike
in a later expiration; puts may move to the same or a lower strike in a later expiration. A casual
call roll-down or put roll-up is not mixed into the default frontier.

The selector returns at most nine distinct candidates and reserves representation for three useful
questions before filling remaining slots:

1. **Lowest cash cost**
2. **Least extra time**
3. **Most strike room**

Candidates may be a net credit, near flat, or a debit paid for more strike room. If the chain has no
directionally valid contract, no later expiration, no positive replacement bid, or no trustworthy
source ask, the row states that reason instead of showing an empty card as reassurance.

## Shared engine

Nibwick alerts, the portfolio Roll Board, and Premium Radar call the same pure selector. A Nibwick
handoff includes the source contract and selected target; Radar refreshes the chain and recomputes
the BTC-ask/STO-bid comparison rather than trusting stale display math.

Every reviewed contract has one stable browser anchor. Nibwick can open that exact Roll Board row;
the Board carries the same anchor into Radar; and Radar can return to the originating contract. The
trail changes navigation only. It does not preserve or imply an executable quote.

## Verification boundary

The board depends on the quote range already loaded for the contract. “No clean roll” means none was
found in that range under these rules; it does not prove that no listed alternative exists. Quote
age, spread, open interest, and volume remain visible context, not a promise of execution quality.
