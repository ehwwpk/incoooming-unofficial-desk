# Incoooming Unofficial Desk

A private, local-first options-income pavilion for Schwab portfolio, covered-call, dividend, and performance analytics.

The first milestone is intentionally small: authenticate, read accounts and positions, preserve the raw broker response, normalize a position snapshot, and prove that the result reconciles. No trading endpoints are implemented.

## Explore the dashboard while Schwab access is pending

The demo command serves a deterministic covered-call simulation through the same application contract used by live data. It models 700 CVX, 800 KTOS, and 500 URNM shares, including weekly, monthly, 13-week, calendar-YTD, and rolling-365 performance; per-name APR/IV and call statistics; a $3,000 monthly objective; lifetime income-adjusted-basis analytics; rolls, closes, expirations, active coverage; and a full execution ledger. It never writes fake records to the real ledger.

```powershell
.\scripts\run-demo.cmd
```

Open `http://127.0.0.1:8182`. Press `Ctrl+C` in the terminal to stop it.

All demo trades, option marks, IV, and Greeks are fictional. Underlying paths are frozen public market-session closes; they are not broker marks or trading guidance.

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

The browser may end on a non-loading local HTTPS page. Copy the entire URL from the address bar and paste it into `auth-complete`; the authorization code is in that URL.

5. Read and store your current accounts and positions, then launch the local dashboard:

```powershell
.\.venv\Scripts\schwab-dashboard.exe sync
.\scripts\run-local.cmd
```

Open `http://127.0.0.1:8182`. The server binds to loopback by default.

## Safety

- Never commit `.env`, `var/`, tokens, exports, or account data.
- OAuth tokens are stored in Windows Credential Manager through `keyring`, not in the repository.
- The Schwab trading adapter only exposes read operations. OAuth token exchange is isolated in a separate client.
- This project is performance-accounting software, not tax or investment advice.

## Project guides

- [Architecture](docs/architecture.md)
- [Phase 0 checklist](docs/phase-0-checklist.md)
- [Data contracts](docs/data-contracts.md)
- [Dashboard contract](docs/dashboard-contract.md)
- [Multi-broker product path](docs/multi-broker-product-path.md)
- [Local-first architecture decision](docs/decisions/0001-local-first-modular-monolith.md)
