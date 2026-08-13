# Public access and cost reality

## Target

Offer a safe Incoooming website where Schwab, Robinhood, and Fidelity users connect accounts and see
nearly the same premium, dividend, risk, and Radar intelligence, while keeping annual operating
cost below $300.

## Verdict

The web application itself can plausibly fit below $300 per year at modest traffic. Automatic,
safe, live connections to all three brokerages for 100–5,000 users cannot currently meet that budget
through a commercial aggregator.

At SnapTrade's published pay-as-you-go prices, real-time connectivity is $2 per connected user per
month and daily read-only connectivity is $1 per connected user per month. That implies:

| Connected users | Real-time annual cost | Daily annual cost |
| ---: | ---: | ---: |
| 100 | $2,400 | $1,200 |
| 1,000 | $24,000 | $12,000 |
| 5,000 | $120,000 | $60,000 |

These figures exclude hosting, support, email, observability, market data, legal work, and taxes.
The Personal plan is free but limited to five total brokerage connections; it is suitable for the
owner's accounts and a proof of concept, not a public 100-user service.

## Why open source does not remove the connection cost

An adapter can normalize an API, but it cannot grant permission to a broker's customer data.

- FDX publishes a royalty-free API specification, consent model, and security guidance. It is a
  standard, not a shared brokerage-access network or a set of credentials.
- Schwab says it does not charge third-party applications or aggregators for client-authorized data
  access, but the fintech must agree to Schwab's data-access terms. That is the best direct path to
  pursue.
- Fidelity Access supplies a secure customer authorization flow through integrated applications and
  aggregators. It is not presented as an unrestricted retail developer API.
- Robinhood does not publish a general API for importing an existing retail equities/options
  account and says official third parties will not ask for the user's password.

Unofficial scraping libraries, browser automation, and collected brokerage passwords are outside
the product boundary. They create security, reliability, terms-of-service, and support risks and do
not become safe because their source code is public.

## The full connection menu

There is no single connection method that is simultaneously free, one-click, multi-broker, live,
and rich enough for option lifecycle accounting. The realistic choices are:

| Path | What the user does | Option-data fit | Cost shape | Verdict |
| --- | --- | --- | --- | --- |
| Direct broker API | Authorizes Incoooming on the broker's consent page | Potentially highest fidelity, but broker-specific | Engineering plus approval, security, and support | Best long-term path where the broker approves it |
| SnapTrade | Uses SnapTrade's hosted connection portal | Strong candidate for positions, options, balances, orders, and activities; still requires a proof of concept per broker | Published per-connected-user or per-sync pricing | Fastest broad proof of concept, not a sub-$300 public service |
| Akoya | Uses an FDX-aligned, user-permissioned connection | Holdings, positions, transactions, open orders, and tax lots are documented; exact option and lifecycle coverage must be tested | Standard plan below 10,000 monthly connections, but dollar pricing is not published and setup fees may apply | Serious production candidate, not a free connector |
| MX | Uses MX account aggregation | Investment holdings and cost basis are documented; refresh and broker-specific option completeness need testing | Sales-led commercial product with no public rate card found | Candidate for an enterprise comparison, not a bootstrap assumption |
| Envestnet Yodlee | Uses Yodlee aggregation | The holdings model explicitly includes call/put type, expiration, strike, and short-position fields | Contracted commercial service | One of the richer schemas on paper; proof of real broker observations is mandatory |
| Morningstar ByAllAccounts | Links an investor account through its component | Positions, transactions, prices, securities, and tax lots; generally nightly after the initial pull | Licensed wealth-management product; pricing is sales-led | Strong accounting/history candidate, not a live chain or cheap public-login layer |
| BridgeFT | Authorizes custodial or held-away feeds | Trade-ready multi-custodial wealth data; market data uses a separate provider license | Enterprise consultation and provider contracts | Architecture fit for a funded wealth product, not the current budget |
| Plaid Investments | Uses Plaid Link | Holdings and investment transactions, including option securities, but commonly overnight rather than live | Commercial; on-demand refresh is an add-on | Useful history/holdings fallback, not Radar's live option source |
| SimpleFIN Bridge | User buys a Bridge subscription and pastes a read-only token | Standard protocol contains balances and transactions, not normalized securities, lots, option contracts, assignments, or Greeks | User-paid $15/year or $1.50/month for up to 25 institutions and 25 apps | Excellent cheap cash-ledger fallback; insufficient for the main option desk |
| CSV, OFX/QFX, or broker statement | Exports a file and imports it | Can be excellent for executed history when a broker export is mapped; not live and formats vary | Near-zero variable cost | Universal fallback and historical backfill |
| Browser-only statement parsing | Selects a local file; parsing occurs on the device | Same limits as the statement, with better privacy | Hosting only | Best near-$300 public beta if automatic freshness is not promised |
| Local desktop companion | Runs a signed local Incoooming service and uses supported direct APIs/imports | Can keep credentials and data local; fidelity depends on the authorized source | Distribution, updates, and support rather than per-user hosting | Best open-source privacy path |
| Scraping or unofficial login automation | Gives software a broker password or logged-in browser | Brittle and impossible to treat as authoritative | Hidden maintenance, security, and legal cost | Rejected |

### What “build it ourselves” can and cannot mean

We can build the entire normalization layer, option ledger, importers, local token vault, sync
workers, capability tests, Radar, and UI. We can also integrate directly with every broker that
grants an approved application access. That removes aggregator markup and gives us control over
quality.

We cannot self-create the broker's customer authorization, institution connectivity, or market-data
redistribution rights. A direct adapter without a broker agreement is only code pointed at a locked
door. Open-source wrappers around undocumented endpoints do not change that.

### Data sufficiency test

Before an integration can be called “Incoooming complete,” test real observations for:

- signed long and short quantities, OCC symbol, put/call, strike, expiration, and multiplier;
- current positions plus transaction depth, premiums, fees, dividends, and cash movements;
- buy-to-open, sell-to-open, buy-to-close, sell-to-close, rolls, expiration, assignment, and exercise;
- tax lots and cost basis without blending tax basis with strategy-adjusted basis;
- quote and observation timestamps, refresh latency, corrections, disconnects, and reauthorization;
- whether chains, IV, Greeks, and real-time marks are included, separately licensed, delayed, or absent.

A polished login is not enough. If a source cannot pass these checks, it becomes a partial-capability
adapter and the missing fields remain visibly unavailable.

## Separate the two logins

`Sign in to Incoooming` and `Connect brokerage` are different security events.

1. Incoooming identity uses a standard passkey or OAuth/OIDC login and creates a tenant.
2. The user selects **Connect brokerage**.
3. Incoooming redirects to the broker's or approved provider's consent page.
4. The broker authenticates the user; Incoooming never receives the broker password.
5. A scoped, revocable token returns to the backend and is encrypted separately from account data.
6. The user can see connection scope, last access, source freshness, and a revoke/delete control.

Tokens must never be placed in browser local storage or application logs. A public system also
requires tenant-level authorization, encrypted backups, audit events, token rotation, webhook
verification, rate limits, incident response, and tested data deletion.

## How to keep the product broker-neutral

The product should have three data layers:

1. **Account truth:** balances, holdings, lots, open positions, executions, dividends, assignments,
   exercises, and fees from a broker, aggregator, or import.
2. **Market intelligence:** common quotes, option chains, Greeks, volatility history, prices, and
   structured events from approved sources.
3. **Incoooming analytics:** one normalized ledger, Premium Radar, campaign accounting, portfolio
   risk, and the shared UI.

This can make 95% of the code and interaction model identical across brokers. It cannot guarantee
95–99% factual coverage when a source omits lots, transaction history, lifecycle events, timely
positions, or option chains. Each connection advertises capabilities and freshness; unavailable
facts stay visibly unavailable.

### Experience tiers

- **Full live:** account truth plus fresh chains/Greeks and structured events. All intelligence.
- **Connected ledger:** current holdings and activity plus a separate approved market-data source.
  Most analytics, with visible source gaps.
- **Imported ledger:** CSV/statement upload plus market data. Full historical analysis through the
  import time, but no claim of automatic current positions.

## Market-data constraint

Brokerage connectivity does not automatically include rights to redistribute real-time options
quotes and Greeks to thousands of website users. OPRA and exchange data have vendor, display, and
non-display policies and fees. Public Radar must confirm redistribution rights with the selected
provider; copying or automatically extracting delayed quote websites is not permitted.

The low-cost first public release should therefore avoid promising real-time public option data
until licensing is contracted. User-authorized broker data may support personal displays subject to
the broker agreement; a common public market-data layer is a separate commercial decision.

## Viable paths

### Path A — personal quality first

- Native Schwab for the owner.
- SnapTrade Personal read-only proof of concept for the owner's Robinhood account.
- CSV/statement import.
- Build and validate Radar on real personal data.

This stays inexpensive and creates the correct engine.

### Path B — public open-source companion

- Publish the local application and adapter SDK.
- Users bring supported personal credentials or imports.
- Account data stays on their machine.
- An optional central site hosts documentation, demo mode, releases, and community features—not
  brokerage tokens.

This can remain under $300, but it is not one-click broker login.

### Path C — public file-first website

- Incoooming account login.
- Encrypted CSV/statement upload or browser-only parsing.
- Delayed/end-of-day intelligence only where licensing permits.
- No broker password and no aggregator bill.

This is the only plausible centralized 100–5,000-user path near the stated budget, but it sacrifices
automatic account freshness.

### Path D — real hosted broker login

- Apply directly for Schwab data-access/commercial approval.
- Ask Fidelity/Akoya for an integrated Fidelity Access relationship.
- Use an approved Robinhood-capable aggregator unless Robinhood opens a direct data program.
- Contract market-data display rights.

This provides the desired experience, but the budget must scale with users or be subsidized.

## Recommended product sequence

1. Do not redesign the current local architecture around cheap hosting yet.
2. Finish native Schwab reconciliation and Premium Radar.
3. Add a versioned `BrokerAdapter` SDK and capability conformance suite.
4. Add broker-specific CSV importers.
5. Test SnapTrade Personal with the owner's Robinhood account.
6. Release a public demo and file-first beta to measure real interest cheaply.
7. Approach Schwab, Fidelity/Akoya, Robinhood, and aggregators with actual usage evidence.
8. Move to commercial connectivity only when pricing, data quality, legal scope, and market-data
   rights are written down.

Before the public Radar labels personalized contracts as attractive or ranks securities using a
user's portfolio, obtain securities counsel. SEC guidance treats algorithmic personalized
investment advice as a potentially regulated activity; “not financial advice” text is not a
substitute for reviewing the actual product behavior.

## Primary references

- [SnapTrade pricing](https://snaptrade.com/pricing)
- [SnapTrade billing](https://docs.snaptrade.com/docs/billing)
- [Schwab data aggregation FAQ](https://www.schwab.com/legal/public-security-tips-popup)
- [Fidelity Access](https://www.fidelity.com/security/fidelity-access-data-security)
- [Robinhood third-party connections](https://robinhood.com/us/en/support/articles/third-party-connections/)
- [FDX API specifications](https://developer.financialdataexchange.org/learn-about-fdx-api-v6-0-0)
- [FDX getting-started guide](https://financialdataexchange.org/common/Uploaded%20files/GettingStartedGuide/Getting%20Started%20with%20Open%20Banking_8-15-23_Optimized.pdf)
- [Plaid Investments refresh behavior](https://plaid.com/docs/investments/)
- [Akoya Accounts & Investments](https://akoya.com/products/investments)
- [Akoya investment API fields](https://docs.akoya.com/reference/investments)
- [Akoya pricing](https://akoya.com/pricing)
- [MX Investment Data](https://www.mx.com/products/investment-data/)
- [MX investment holdings fields](https://docs.mx.com/api-reference/platform-api/v20111101/reference/investment-holdings)
- [Yodlee holdings and option fields](https://developer.yodlee.com/resources/yodlee/data-model/docs/holdings)
- [Morningstar ByAllAccounts investor FAQ](https://developers.byallaccounts.morningstar.com/docs/what-is-investor-account-aggregation)
- [BridgeFT WealthTech API](https://docs.bridgeft.com/docs/welcome-v26)
- [SimpleFIN protocol](https://www.simplefin.org/protocol.html)
- [SimpleFIN Bridge pricing](https://beta-bridge.simplefin.org/)
- [OPRA fee schedule](https://cdn.opraplan.com/documents/OPRA_Fee_Schedule.pdf)
- [Cboe options market data](https://www.cboe.com/data/market-data-services/us/options)
- [SEC robo-adviser guidance](https://www.sec.gov/newsroom/press-releases/2017-52)
- [Cloudflare Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/)
