# Connect Schwab to Incoooming on Windows

This connects your own Schwab account so Incoooming can show your positions, activity, and market
data. You'll sign in on Schwab's website and choose which accounts to share. Incoooming never
asks for your Schwab password or places trades.

New here? [Get the demo running first](getting-started.md). You can also give your coding agent
the [setup prompt](../README.md#want-your-coding-agent-to-help) and have it walk through this guide
with you. You enter the secrets and complete the broker login yourself.

Schwab controls developer access, portal labels, and approval time. Check its portal if the steps
below differ from the current site.

## Requirements

- A Schwab brokerage account
- Windows 10 or 11
- [Python 3.12, 3.13, or 3.14](https://www.python.org/downloads/windows/)
- An extracted copy of this repository
- A browser

Keep the Python launcher enabled if the installer offers it. Setup checks `py` first and also
supports a compatible `python` command. Extract a GitHub ZIP before running anything. If the
standalone demo is open, stop it with `Ctrl+C` in its terminal before continuing.

## 1. Request Individual Trader API access

1. Register or sign in at the [Schwab Developer Portal](https://developer.schwab.com/).
2. Add the **Individual Developer** role if the portal asks for it.
3. Open **API Products**, choose **Individual Developers**, and request
   **Trader API - Individual** access.
4. Wait until Schwab approves the request.

## 2. Create an app

After access is approved:

1. Open the [Apps dashboard](https://developer.schwab.com/dashboard/apps).
2. Create an app with the account/trading and market-data products available under the Individual
   Trader API.
3. If the portal asks for an order limit, set it to `0`. Incoooming does not place orders.
4. Register this callback URL exactly:

```text
https://127.0.0.1:8182/
```

5. Wait until the app is ready for use.
6. Keep the app's client ID and client secret handy for the next step. Enter them in your local
   settings file, not in an agent chat.

The scheme, address, port, and final slash in the callback URL must match.

## 3. Configure Incoooming

Open PowerShell in the project folder. Run bootstrap if you haven't already, then create your
settings file if it doesn't exist yet:

```powershell
.\scripts\bootstrap.cmd
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Set these three values in `.env`:

```text
SCHWAB_APP_KEY=paste-your-client-id-here
SCHWAB_APP_SECRET=paste-your-client-secret-here
SCHWAB_CALLBACK_URL=https://127.0.0.1:8182/
```

Save the file, close Notepad, and check the setup:

```powershell
.\.venv\Scripts\schwab-dashboard.exe doctor
```

Look for `Schwab credentials configured: True`. A missing token is normal at this point: you
haven't signed in yet. This check doesn't print your key or secret.

## 4. Authorize the app

Run the guided connector:

```powershell
.\scripts\connect-schwab.cmd
```

It prepares the database and opens Schwab. Sign in, choose the accounts to share, and approve
access. Schwab then redirects the browser to a URL beginning with:

```text
https://127.0.0.1:8182/?code=...
```

**The final page may show a connection or certificate error. That's expected for this login
flow.** Don't reload it. Press `Ctrl+L`, then `Ctrl+C` once to copy the whole address. The connector
uses its one-time code to finish login, clears the copied URL, fetches your data, and starts
Incoooming in the background. Keep this URL out of chats, screenshots, and public issues.

If clipboard capture is unavailable, press `Ctrl+C` to stop the connector and use the manual flow:

```powershell
.\.venv\Scripts\schwab-dashboard.exe db-upgrade
.\.venv\Scripts\schwab-dashboard.exe auth-url
.\.venv\Scripts\schwab-dashboard.exe auth-complete
.\.venv\Scripts\schwab-dashboard.exe sync
.\scripts\run-local.cmd
```

Open the printed link, approve access, then paste the complete callback URL into `auth-complete` and
press Enter. The prompt is hidden because the URL contains a short-lived, one-time authorization
code.

## 5. Sync and open the desk

The guided connector has already synced and started the desk. Visit
[http://127.0.0.1:8182](http://127.0.0.1:8182), choose **Schwab live**, and open the desk. If you
used the manual flow, leave its server window open.

You're connected when a sync finishes and the desk shows a recent successful sync time. A saved
login token by itself doesn't confirm that the account data was fetched successfully.

## Later use

After restarting Windows, open PowerShell in the project directory and run:

```powershell
.\scripts\run-local.cmd
```

The local server requests a refresh after startup and every 15 minutes while it is open. It does
not install a background service. Use `SYNC NOW` for a manual refresh or run
`.\scripts\restart-local.cmd` to replace a verified stale copy. Press `Ctrl+C` in the server window
to stop it.

If the desk asks you to reconnect Schwab, run `connect-schwab.cmd` again. It always creates a new
authorization request.

## Troubleshooting

### Credentials are not configured

Confirm that `.env` is in the project directory and contains nonblank values for
`SCHWAB_APP_KEY` and `SCHWAB_APP_SECRET`.

### Schwab rejects the callback or code

Confirm that the callback in the Schwab app and `.env` is exactly
`https://127.0.0.1:8182/`. An authorization code is short-lived and works once. Generate a new URL
and repeat the approval if the code was already used or expired.

### The callback page does not load

This is expected. In the guided flow, copy the complete address once. In the manual flow, paste it
into `auth-complete`.

### Port 8182 is already in use

Check [http://127.0.0.1:8182](http://127.0.0.1:8182). If Incoooming is already open, use that server
or run `.\scripts\restart-local.cmd`. The launcher will not stop an unrelated process.

### The desk has no current positions

Use `SYNC NOW` or stop the server and run `sync` followed by `run-local.cmd`. Check the server output
and Data Health if the refresh fails.

## Protect private data

- Never commit or share `.env`, `var/`, a database, a broker export, an OAuth callback URL, or a
  token.
- OAuth tokens are stored through Windows Credential Manager.
- The local server is restricted to IPv4 loopback. Do not expose it through a reverse proxy,
  tunnel, or router port.
- The Schwab integration reads data and has no order endpoints.

## Official Schwab pages

- [Developer Portal](https://developer.schwab.com/)
- [API Products](https://developer.schwab.com/products)
- [Apps dashboard](https://developer.schwab.com/dashboard/apps)
- [User Guides](https://developer.schwab.com/user-guides)
