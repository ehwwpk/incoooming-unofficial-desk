# Incoooming data source gateway

## Product contract

`/sources` is the one place where an Incoooming user chooses which book the interface reads. It is
intentionally separate from the trading desk so onboarding choices do not compete with daily options
work.

Available source keys are:

- `schwab`: the canonical live SQLite ledger populated by the approved read-only Schwab adapter;
- `csv:<dataset-id>`: one immutable imported dataset;
- `demo`: stable fictional fixtures.

The selected key is stored in an HTTP-only, same-site local cookie. It is a reader selector, not an
authentication token. OAuth tokens remain in Windows Credential Manager, and imported rows remain
in the local database. Every page and workspace receives the same selected source. The persistent
`BOOK` link returns to the gateway.

## Non-negotiable boundaries

- Sources are never silently combined.
- Selecting a source never starts a broker sync or a Radar lookup.
- Incoooming cannot infer that one CSV export contains balances, history, lots, Greeks, or
  dividends merely because it contains positions.
- CSV import must preview detected formats and row dispositions before a dataset is committed.
- No workflow asks for brokerage usernames or passwords.
- A future hosted login must use provider-approved OAuth or a vetted connection provider.
- Trading endpoints remain outside the application.

## Personal versus public Schwab onboarding

The current local build uses an Individual Trader API application: the owner supplies an approved
app key and secret once, then authorizes the account through Schwab OAuth. This is appropriate for
the owner's local tool. It is not a general-public login design.

A public `Connect Schwab` button requires Schwab to approve the product's own client registration
and redirect flow. End users should authorize that client; they should not create developer apps or
paste secrets into a hosted site.
