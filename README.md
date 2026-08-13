# Incoooming

**Premium in. Noise out.**

Incoooming is a private, local-first desk for people who sell options, collect dividends, and want
to understand the whole book without wrestling a brokerage statement. The extra `oo` is deliberate:
it is the little desk yell when another credit hits the ledger.

**Schwab user, not a developer?** Start with the plain-language
[Schwab connection guide](docs/getting-started-schwab.md). It walks from portal registration to the
first live sync without assuming you know Python or OAuth.

It answers a few practical questions quickly:

- How much option and dividend cash actually arrived?
- What is open now, how close is it to the strike, and how many days remain?
- How much of each contract's original time and premium value remains?
- Which expirations, assignments, dividends, or fast-moving names deserve a look?
- Which broker records support every number on screen?

## Open the right book

The first screen is a source gateway, not a brokerage-password form. It offers three deliberately
separate paths:

- **Schwab live** requires each self-hosted user to obtain Schwab Developer API approval and connect
  their own app key, secret, callback URL, and OAuth authorization on their computer. Incoooming
  does not provide or bypass that approval.
- **Import CSV** creates a new local book from exported positions and activity. Multiple files can
  be imported together, but separate imports are never silently merged.
- **Demo book** opens the fictional operator desk.

The `BOOK` control in the top-right of every desk and workspace returns to this gateway, so a user
can move from Schwab to a Robinhood or Fidelity export without restarting the server. CSV rows are
kept with their raw source values and normalized records; unsupported rows stop or surface warnings
instead of being guessed into financial facts.

To smoke-test the file path without using personal data, open `BOOK`, choose `Import CSV`, select
`Generic / template`, and upload both files in [`examples/csv`](examples/csv). The resulting isolated
mock book contains 2,000 shares across CVX, KTOS, and URNM, seven short calls, three opening premium
events, and one dividend. The same files are exercised by the automated dashboard integration test.

Today, the personal Schwab path still requires the user's own approved Individual Trader API app
key, secret, and OAuth authorization. That is not the intended public onboarding experience. A
hosted release would need Schwab's provider-approved OAuth flow (or a vetted aggregator) so ordinary
users click `Connect Schwab` without creating developer credentials. Incoooming never asks for or
stores a brokerage username and password.

The Schwab connection is read-only and auditable. Incoooming preserves raw account, transaction,
quote, option-chain, and daily-price responses; normalizes positions, executions, dividends,
interest, expirations, assignments, and market observations; and reconciles the cash ledger. It is
an analytics desk, not a broker or trading bot. No trading endpoints are implemented.

## Take the demo desk for a spin

The demo uses the same application path as live data with an isolated fictional book: 700 CVX,
800 KTOS, and 500 URNM shares. It includes rolling 4-week, quarterly, YTD, and rolling-365 cash;
per-stock APR, IV, calls, assignments, rolls, expirations, charts, and lifetime capital-recovery
context. Demo option trades, marks, IV, and Greeks are fictional and never enter the live ledger.

```powershell
.\scripts\run-demo.cmd
```

Open `http://127.0.0.1:8182`. Press `Ctrl+C` in the terminal to stop it.

The main Desk keeps the daily job compact: realized option and dividend cash, live obligations, one
row per stock, and only the exceptions worth reviewing. Stocks open on demand for a taller price and
execution chart, the first three contracts beside it, and a two-column option shelf below when the
book is larger. The Open Options workspace keeps portfolio totals visible, opens the expiration
calendar by default, and remembers which supporting sections you open or close. Results labels the
actual normalized-history coverage and never turns unavailable months into zero-dollar results.
Volatility Lab and Data Health live behind `TOOLS`; each tool can open in the current page or its own
window.

Underlying demo paths use frozen public market-session closes. They are not broker marks or trading
guidance.

## Quick start on Windows

For the careful, screen-by-screen version—including Schwab approval, exact portal fields, credential
mapping, the strange local callback page, restarts, and common failures—use the
[Schwab connection guide](docs/getting-started-schwab.md).

1. Create an Individual Trader API application at the [Schwab Developer Portal](https://developer.schwab.com/). Record the exact callback URL configured for the app.
2. In PowerShell, from this project directory:

```powershell
.\scripts\bootstrap.cmd
Copy-Item .env.example .env
```

3. Edit `.env` and set `SCHWAB_APP_KEY`, `SCHWAB_APP_SECRET`, and the exact `SCHWAB_CALLBACK_URL` registered with Schwab.
4. Initialize the database and complete the manual OAuth flow:

```powershell
.\.venv\Scripts\schwab-dashboard.exe db-upgrade
.\.venv\Scripts\schwab-dashboard.exe auth-url
.\.venv\Scripts\schwab-dashboard.exe auth-complete
```

The browser may end on a non-loading local HTTPS page. Copy the entire URL from the address bar and
paste it into `auth-complete`; the authorization code is inside that URL.

5. Read and store current accounts and positions, one year of transaction history, current option
   chains and Greeks, and one year of daily underlying prices; then launch the local dashboard:

```powershell
.\.venv\Scripts\schwab-dashboard.exe sync
.\scripts\run-local.cmd
```

Open `http://127.0.0.1:8182`, choose `Schwab`, and open the live book. The server binds to your own
computer by default.

Premium Radar is an explicit, ticker-first research tool under `TOOLS`. It never suggests a random
stock and never places an order. A lookup uses a dedicated market-data request/cache and cannot
delay or fail normal account synchronization. It reads the currently open book only for position,
covered-lot, and reserved-cash context. The personal defaults are 5–60 DTE and a 5% simple
annualized bid-based premium floor. Those are editable policies rather than engine limits, so a
user can inspect shorter expirations, 90-day contracts, or listed LEAPS without changing code.
Radar returns zero to nine distinct comparisons rather than padding the page with weak premium.

## Keeping the live desk current

Live mode refreshes Schwab automatically when the local server starts and every 15 minutes while
that server remains open. The top-right status shows whether the ledger is synced, syncing, needs
attention, or needs Schwab reauthorization. `SYNC NOW` requests the same protected full refresh on
demand. The page checks sync status every 30 seconds and reloads itself after a newer successful
snapshot is committed.

A normal browser refresh only rereads the local SQLite ledger; it does not itself call Schwab. That
keeps page loads fast and prevents overlapping API jobs. The server-side coordinator serializes
account, transaction, quote, option-chain, Greek, and daily-price ingestion, and records a full-run
success or failure so a partial refresh cannot be presented as fully current.

The defaults work without adding anything to an existing `.env`. They can be changed with:

```text
SCHWAB_AUTO_SYNC_ENABLED=true
SCHWAB_AUTO_SYNC_INTERVAL_SECONDS=900
SCHWAB_AUTO_SYNC_STARTUP_DELAY_SECONDS=2
```

Automatic refresh exists only while `run-local.cmd` is running; Incoooming does not install a
hidden Windows background service.

## Safety

- Never commit `.env`, `var/`, tokens, exports, or account data.
- OAuth tokens live in Windows Credential Manager through `keyring`, not in the repository.
- The Schwab adapter exposes read operations only. Token exchange is isolated in a separate client.
- Incoooming is performance-accounting software, not tax or investment advice.

## Project guides

- [Connect Schwab to Incoooming](docs/getting-started-schwab.md)
- [Architecture](docs/architecture.md)
- [Phase 0 checklist](docs/phase-0-checklist.md)
- [Data contracts](docs/data-contracts.md)
- [Dashboard contract](docs/dashboard-contract.md)
- [Multi-broker product path](docs/multi-broker-product-path.md)
- [Operator workflows](docs/product/operator-workflows.md)
- [Capability roadmap](docs/product/capability-roadmap.md)
- [Premium Radar plan](docs/product/premium-radar.md)
- [Data source gateway](docs/systems/data-source-gateway.md)
- [CSV import contract](docs/systems/csv-import.md)
- [Public access and cost reality](docs/product/public-access-economics.md)
- [Truth Engine](docs/systems/truth-engine.md)
- [Open Risk Board](docs/systems/open-risk-board.md)
- [Attribution Lab](docs/systems/attribution-lab.md)
- [Volatility Lab](docs/systems/volatility-lab.md)
- [Workspace System](docs/systems/workspace-system.md)
- [Independent workspace shell](docs/workspaces/workspace-shell.md)
- [Broker adapter strategy](docs/integrations/broker-adapter-strategy.md)
- [Verified Schwab live contract](docs/integrations/schwab-live-contract.md)
- [Integrated platform plan](docs/systems/integrated-platform-plan.md)
- [Local-first architecture decision](docs/decisions/0001-local-first-modular-monolith.md)
