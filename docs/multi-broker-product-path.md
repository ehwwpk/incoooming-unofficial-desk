# Multi-broker product path

## Objective

Let a person use Incoooming without becoming a broker API developer or sharing brokerage credentials with the application.

The accounting domain must remain broker-neutral. Schwab, an aggregator, and file imports should all produce the same normalized accounts, positions, executions, option lifecycle events, dividends, and cash movements.

## Release paths

### Personal and open-source local installation

- Keep the direct Schwab Individual adapter for the owner's account.
- Allow bring-your-own Schwab developer credentials for advanced self-hosters.
- Add broker statement and transaction-file imports as the universal fallback.
- Store tokens in the operating-system credential vault and account data only on the user's machine.
- Do not require a central Incoooming account.

This path is private and inexpensive, but it is not a one-click experience for general users.

### Hosted public application

1. The user creates an Incoooming account.
2. The user clicks **Connect brokerage** and completes a broker or approved aggregator consent flow.
3. The connection provider returns a scoped connection token; Incoooming never receives the brokerage password.
4. Background workers ingest read-only accounts, holdings, transactions, option positions, dividends, expirations, assignments, and exercises.
5. Broker adapters normalize those observations into the existing internal ledger.
6. A separate licensed market-data provider supplies current option marks, IV, Greeks, and underlying prices when the brokerage feed does not.
7. Every dashboard value retains source, observation time, and reconciliation status.

The hosted system needs tenant isolation, encrypted token storage, token rotation, data deletion, audit logs, rate limiting, a privacy policy, and reviewed market-data display rights. Read-only should remain the first public scope; trading creates materially more risk and operational burden.

## Current connectivity assessment

### Schwab

The direct Individual Trader API is appropriate for the owner's self-directed account. A public multi-user product must not assume that one Individual app can serve unrelated customers; commercial or partner approval must be confirmed with Schwab before offering a shared connection flow.

### Robinhood

Robinhood's public developer documentation currently describes its Crypto Trading API, not a general stock-and-options account API. Treat a direct Robinhood equities adapter as unavailable unless Robinhood explicitly offers and approves one. An approved aggregation provider is the realistic near-term path.

### Fidelity

Fidelity Access provides user-authorized third-party data sharing without giving the third party a Fidelity password. Access is generally mediated through approved applications and data aggregators rather than a casual retail developer app.

### Aggregation candidates

- [SnapTrade](https://snaptrade.com/brokerage-api) is the stronger first evaluation for this product. It advertises Schwab, Fidelity, and Robinhood connectivity; returns option positions; and normalizes dividend, expiration, assignment, and exercise activity types.
- [Plaid Investments](https://plaid.com/docs/investments/) offers broad holdings and investment-transaction coverage, including option securities. Its standard investment refresh is commonly overnight, and Fidelity access has plan and enablement constraints, so it is more suitable for portfolio history than an intraday options desk.

Provider marketing is not a contract. Before selection, run a proof of concept against each target broker and verify short-option signs, OCC symbols, contract multipliers, premiums, fees, assignments, exercises, dividends, transaction depth, refresh latency, and disconnection behavior.

## Recommended sequence

1. Finish and validate the direct read-only Schwab integration for the owner.
2. Lock the broker-neutral execution and lifecycle schema using real Schwab observations.
3. Add a CSV/statement import adapter for portability and historical backfill.
4. Prototype a read-only SnapTrade adapter against sandbox and one approved real connection.
5. Add licensed option market data only after position and cash accounting reconcile.
6. Build multi-user identity, tenancy, consent, deletion, and operational controls.
7. Invite a very small read-only beta before any public launch.

## Product boundaries

- Premium cash is not total return.
- Current option marks are not executed close debits.
- Assignment is a disposition, not automatically a loss.
- Broker statements remain authoritative when integrations disagree.
- Missing or stale data must be visible, never silently estimated as broker truth.
