# Incoooming

**Premium in. Noise out.**

Incoooming is a private, local-first desk for people who sell options, collect dividends, and want
to understand the whole book without wrestling a brokerage statement. The extra `oo` is deliberate:
it is the little desk yell when another credit hits the ledger.

It answers a few practical questions quickly:

- How much option and dividend cash actually arrived?
- What is open now, how close is it to the strike, and how many days remain?
- How much of each contract's original time and premium value remains?
- Which expirations, assignments, dividends, or fast-moving names deserve a look?
- Which broker records support every number on screen?

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
row per stock, and only the exceptions worth reviewing. Stocks open on demand for charts and
contracts. The Calls workspace keeps portfolio totals visible while expiration and contract
sections stay folded until their headers are clicked. Results, Volatility Lab, and Data Health live
behind `TOOLS` and can open in the current page or their own window.

Underlying demo paths use frozen public market-session closes. They are not broker marks or trading
guidance.

## Quick start on Windows

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

Open `http://127.0.0.1:8182`. The server binds to your own computer by default.

## Safety

- Never commit `.env`, `var/`, tokens, exports, or account data.
- OAuth tokens live in Windows Credential Manager through `keyring`, not in the repository.
- The Schwab adapter exposes read operations only. Token exchange is isolated in a separate client.
- Incoooming is performance-accounting software, not tax or investment advice.

## Project guides

- [Architecture](docs/architecture.md)
- [Phase 0 checklist](docs/phase-0-checklist.md)
- [Data contracts](docs/data-contracts.md)
- [Dashboard contract](docs/dashboard-contract.md)
- [Multi-broker product path](docs/multi-broker-product-path.md)
- [Operator workflows](docs/product/operator-workflows.md)
- [Capability roadmap](docs/product/capability-roadmap.md)
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
