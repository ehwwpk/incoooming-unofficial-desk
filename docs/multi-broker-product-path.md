# Incoooming multi-broker product path

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
7. Every Incoooming value retains source, observation time, and reconciliation status.

The hosted system needs tenant isolation, encrypted token storage, token rotation, data deletion, audit logs, rate limiting, a privacy policy, and reviewed market-data display rights. Read-only should remain the first public scope; trading creates materially more risk and operational burden.

## Current connectivity assessment

## Broker truth and market truth are separate

Incoooming must not require every brokerage adapter to supply a complete analytical market feed.
The provider boundaries are intentionally different:

- **Broker adapters** supply account truth: accounts, balances, held and short positions, orders,
  executions, cash movements, cost basis when available, and lifecycle events such as assignment.
- **Market-data adapters** supply market truth: underlying quotes and bars, option chains, bid/ask,
  open interest, implied volatility, Greeks, and corporate-action or dividend reference data.
- **The analytics engine** joins normalized account truth to normalized market truth and preserves the
  provider, observation time, and freshness of every derived result.

The live Schwab installation can use Accounts and Trading Production for the book and Market Data
Production for market intelligence. A future Fidelity, Robinhood, aggregator, or CSV book can use
the same market-data adapter without pretending that its brokerage connection supplied the chain.
Market capabilities should be selected independently: one licensed provider may supply live OPRA
quotes and Greeks while another supplies corporate actions or long price history.

Provider substitution must never become silent data mixing. A chain, its option marks, underlying
spot, IV, and Greeks need compatible observation times; stale or estimated fields remain labeled.
Yahoo Finance scraping is acceptable only as an explicitly non-authoritative development aid, not
the public product's market-data backbone. Yahoo does not document a supported public Finance API,
and its API terms prohibit automated access outside its APIs. Production candidates must have a
documented options feed and display or redistribution terms appropriate to the release model.

### Schwab

The direct Individual Trader API is appropriate for the owner's self-directed account. A public multi-user product must not assume that one Individual app can serve unrelated customers; commercial or partner approval must be confirmed with Schwab before offering a shared connection flow.

### Robinhood

Robinhood's public developer documentation currently describes its Crypto Trading API, not a
general API for reading an existing retail stock-and-options account. Robinhood also says supported
third-party services should not ask for the user's Robinhood password, and API control of a normal
Robinhood account requires written authorization. Do not build credential scraping or rely on an
unofficial API.

Robinhood Agentic Trading exposes documented equity and option tools for a dedicated Agentic
account. Treat that as a separate future adapter evaluation, not proof that an existing standard
Robinhood brokerage account can be imported directly.

### Fidelity

Fidelity Access provides user-authorized third-party data sharing without giving the third party a Fidelity password. Access is generally mediated through approved applications and data aggregators rather than a casual retail developer app.

### Aggregation candidates

- [SnapTrade](https://snaptrade.com/brokerage-api) is the stronger first evaluation for this product.
  It supports Schwab, Fidelity, and Robinhood connections and exposes accounts, positions, options,
  balances, orders, and activities through a hosted connection portal. Personal use currently
  allows up to five brokerage connections on the free plan. A public application uses SnapTrade
  Commercial and pays for connected users or syncs; it is not free infrastructure at scale.
- [Plaid Investments](https://plaid.com/docs/investments/) offers broad holdings and investment-
  transaction coverage, including option securities. Standard investment holdings are generally
  refreshed overnight and on-demand refresh is an add-on with institution limitations. It is a
  history and holdings fallback, not the sole live option-chain and Greeks source for Premium Radar.
- Akoya, MX, Envestnet Yodlee, Morningstar ByAllAccounts, and BridgeFT all document investment-data
  products. Their schemas and operating models differ: Yodlee explicitly models option type,
  expiration, strike, and short holdings; ByAllAccounts is generally nightly and wealth-accounting
  oriented; BridgeFT is a multi-custodial wealth platform; and Akoya is API-only and FDX-aligned.
  Treat all five as contracted production candidates, not free infrastructure. Run the same real-
  account conformance suite before choosing one.
- SimpleFIN Bridge is unusually inexpensive because the user pays $15/year, but its standard data
  model is balances and transactions. It can feed cash history, not replace positions, lots, option
  lifecycle events, chains, marks, IV, or Greeks.

The maintained comparison and cost analysis lives in
[`product/public-access-economics.md`](product/public-access-economics.md).

Provider marketing is not a contract. Before selection, run a proof of concept against each target broker and verify short-option signs, OCC symbols, contract multipliers, premiums, fees, assignments, exercises, dividends, transaction depth, refresh latency, and disconnection behavior.

## Recommended sequence

1. Keep the now-working direct read-only Schwab integration as the highest-fidelity personal path.
2. Lock the broker-neutral execution and lifecycle schema using reconciled real Schwab observations.
3. Use the implemented isolated CSV books as the no-login portability and history-backfill path;
   certify broker-specific export variants only after sanitized fixture tests.
4. Prototype SnapTrade Personal in read-only mode for the owner's Robinhood account.
5. Verify short signs, OCC symbols, lifecycle events, history depth, refresh latency, and disconnect
   behavior against the real account before calling the adapter supported.
6. If public demand justifies hosted operations, move the same connection boundary to SnapTrade
   Commercial or negotiate direct broker access. Add licensed option market data where aggregation
   lacks timely chains and Greeks.
7. Build multi-user identity, tenancy, consent, revocation, deletion, and operational controls before
   inviting a small read-only beta.

## What “log in with my broker” actually means

The public user creates an Incoooming account, clicks **Connect brokerage**, and is redirected to the
broker's or approved aggregator's consent portal. The platform owns the integration credentials;
the user does not need a developer account or paste API keys. Incoooming receives a scoped token,
never the brokerage password.

An open-source self-hosted copy has three different choices: bring personal broker developer
credentials where supported, connect through a personal aggregation plan, or import files. Free
source code does not make commercial connectivity, live market data, secure hosting, or compliance
free.

## Product boundaries

- Premium cash is not total return.
- Current option marks are not executed close debits.
- Assignment is a disposition, not automatically a loss.
- Broker statements remain authoritative when integrations disagree.
- Missing or stale data must be visible, never silently estimated as broker truth.

## Primary references

- [Schwab token-based third-party access](https://www.schwab.com/legal/public-security-tips-popup)
- [Robinhood third-party connections](https://robinhood.com/us/en/support/articles/third-party-connections/)
- [Robinhood Agentic Trading](https://robinhood.com/us/en/support/articles/trading-with-your-agent/)
- [SnapTrade personal and commercial modes](https://docs.snaptrade.com/docs/personal-vs-commercial)
- [SnapTrade pricing](https://snaptrade.com/pricing)
- [Plaid Investments](https://plaid.com/docs/investments/)
