# Connect Schwab to Incoooming on Windows

This guide connects a local copy of Incoooming to Schwab's Individual Trader API. Schwab handles
the login and account consent on its website. Incoooming never asks for your Schwab password.

Schwab controls developer access, portal labels, and approval time. Check its portal if the steps
below differ from the current site.

## Requirements

- A Schwab brokerage account
- Windows 10 or 11
- [Python 3.12, 3.13, or 3.14](https://www.python.org/downloads/windows/)
- An extracted copy of this repository
- A browser

Keep the Python Launcher enabled when installing Python from python.org. The setup script uses the
`py` command. If you downloaded a ZIP from GitHub, extract it before running the commands.

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
3. Set the order limit to `0`. Incoooming does not place orders.
4. Register this callback URL exactly:

```text
https://127.0.0.1:8182/
```

5. Wait until the app is ready for use.
6. Copy the app's client ID and client secret to a private location for the next step.

The scheme, address, port, and final slash in the callback URL must match.

## 3. Configure Incoooming

Open PowerShell in the extracted project directory and run:

```powershell
.\scripts\bootstrap.cmd
Copy-Item .env.example .env
notepad .env
```

Set these three values in `.env`:

```text
SCHWAB_APP_KEY=paste-your-client-id-here
SCHWAB_APP_SECRET=paste-your-client-secret-here
SCHWAB_CALLBACK_URL=https://127.0.0.1:8182/
```

Do not add quotation marks. Save the file, close Notepad, and check the setup:

```powershell
.\.venv\Scripts\schwab-dashboard.exe doctor
```

`Schwab credentials configured: True` should appear. A missing token is expected before the next
step. The command does not print the key or secret.

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

The page may show a connection or certificate error because no HTTPS server is listening there.
Do not reload it. Press `Ctrl+L`, then `Ctrl+C` once. The connector recognizes the exact callback,
clears the copied URL, exchanges the one-time code, syncs the ledger, and starts Incoooming in the
background. Do not paste the URL into a public issue, screenshot, or chat.

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

A stored token only means authorization data is available. The connection is confirmed when a sync
finishes and the desk shows a recent successful sync time.

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
