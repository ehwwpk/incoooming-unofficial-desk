# Incoooming

**Premium in. Noise out.**

Incoooming is the software. It is a private, local-first desk for people who sell covered calls and
cash-secured puts, collect dividends, and want the cash clock, the open overlay, and the source
records kept apart. The extra `oo` is deliberate: it is the little desk yell when another credit
hits the ledger.

**Schwab user, not a developer?** Start with the plain-language
[Schwab connection guide](docs/getting-started-schwab.md). It walks from portal registration to the
first live sync without assuming you know Python or OAuth.

It answers a few practical questions quickly:

- How much option and dividend cash actually arrived?
- What is open now, how close is it to the strike, and how many days remain?
- How much of each contract's original time and premium value remains?
- Which nearby listed rolls can be compared with honest two-leg cash math?
- Which expirations, assignments, dividends, or fast-moving names deserve a look?
- Which broker records support every number on screen?

## Open the right book

The first screen is a source gateway, not a brokerage-password form. It offers three deliberately
separate paths:

- **Schwab live** requires each self-hosted user to obtain Schwab Developer API approval and connect
  their own app key, secret, callback URL, and OAuth authorization on their computer. Incoooming
  does not provide or bypass that approval.
- **Import CSV** creates a new local book from exported positions and activity. Multiple files can
  be imported together, but separate imports are never silently merged. Schwab, Fidelity,
  Robinhood, Webull, IBKR, and Incoooming-template adapters verify the export before import.
- **Demo book** opens the fictional operator desk.

The `BOOK` control in the top-right of every desk and workspace returns to this gateway, so a user
can move from Schwab to a Robinhood or Fidelity export without restarting the server. CSV rows are
previewed before commit and kept with their raw source values, row numbers, dispositions, and
normalized records. Unsupported or uncertain rows stay out of the ledger instead of being guessed
into financial facts.

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
campaign chart, the first three contracts beside it, and a two-column option shelf below when the
book is larger. Calls use stable `C#` campaign labels and puts use `P#`; rolls keep one identity while
every execution remains auditable. Routine share trades are netted into one optional daily marker.
The Open Options workspace starts with Nibwick's portfolio Roll Board, then the expiration calendar
and full contract register. The board compares later listed replacements as planning quotes: buy the
open short at its ask, sell the replacement at its bid, keep the next nearby expiries and strikes,
and never treat that math as an order. Results labels the actual normalized-history coverage and
never turns unavailable months into zero-dollar results. Premium Radar, Volatility Lab, and Data
Health live behind `TOOLS`; each tool can open in the current page or its own window.

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
   chains and Greeks, and one year of daily underlying prices; then launch Incoooming:

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
Radar returns zero to nine distinct comparisons rather than padding the page with weak premium. A
Nibwick or Roll Board handoff refreshes the same nearby listed ladder against a current chain
instead of reusing a stale desk quote.

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

If Incoooming is already running, `run-local.cmd` checks the local server's application ID,
process ID, and code fingerprint. It leaves an unrelated process alone, reuses a current server,
and replaces a verified stale Incoooming process. For an intentional one-click restart that returns
after the replacement passes its health check, run:

```powershell
.\scripts\restart-local.cmd
```

The top-right health dot distinguishes a ready local server from an unavailable freshness check. An
unexpected page failure shows a local recovery screen; it never clears or recreates the ledger.

## Safety

- Never commit `.env`, `var/`, tokens, exports, or account data.
- OAuth tokens live in Windows Credential Manager through `keyring`, not in the repository.
- The Schwab adapter exposes read operations only. Token exchange is isolated in a separate client.
- Incoooming is performance-accounting software, not tax or investment advice.

## Project guides

The software title is **Incoooming**. The local CLI is still invoked as `schwab-dashboard`; that is
a script name, not a second product.

- [Connect Schwab to Incoooming](docs/getting-started-schwab.md)
- [Incoooming architecture](docs/architecture.md)
- [Original Schwab access checklist](docs/phase-0-checklist.md)
- [Incoooming data contracts](docs/data-contracts.md)
- [Incoooming dashboard contract](docs/dashboard-contract.md)
- [Incoooming multi-broker product path](docs/multi-broker-product-path.md)
- [Incoooming operator workflows](docs/product/operator-workflows.md)
- [Incoooming capability roadmap](docs/product/capability-roadmap.md)
- [Incoooming Premium Radar](docs/product/premium-radar.md)
- [Incoooming Nibwick Roll Board](docs/product/nibwick-roll-board.md)
- [Incoooming option campaign chart](docs/product/option-campaign-chart-redesign.md)
- [Incoooming data source gateway](docs/systems/data-source-gateway.md)
- [Incoooming CSV import contract](docs/systems/csv-import.md)
- [Incoooming public access and cost reality](docs/product/public-access-economics.md)
- [Incoooming Truth Engine](docs/systems/truth-engine.md)
- [Incoooming Open Risk Board](docs/systems/open-risk-board.md)
- [Incoooming Attribution Lab](docs/systems/attribution-lab.md)
- [Incoooming Volatility Lab](docs/systems/volatility-lab.md)
- [Incoooming Workspace System](docs/systems/workspace-system.md)
- [Incoooming workspace shell](docs/workspaces/workspace-shell.md)
- [Incoooming broker adapter strategy](docs/integrations/broker-adapter-strategy.md)
- [Incoooming Schwab live contract](docs/integrations/schwab-live-contract.md)
- [Incoooming integrated platform plan](docs/systems/integrated-platform-plan.md)
- [Incoooming local-first architecture decision](docs/decisions/0001-local-first-modular-monolith.md)
