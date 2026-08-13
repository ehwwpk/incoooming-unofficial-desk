# Connect Schwab to Incoooming on Windows

This is the current self-hosted route for a Schwab user. You create a personal Schwab developer
app, keep its credentials on your own computer, and authorize only the accounts you want
Incoooming to read.

You do **not** give Incoooming your Schwab username or password. Schwab handles that login on its
own website.

Already have a Schwab app marked **Ready For Use**? Skip to [step 4](#4-put-the-three-app-values-in-incoooming).
Already filled in `.env`? Skip to [step 5](#5-authorize-schwab-and-build-the-first-book).

> **Time:** about 20 minutes of setup, plus Schwab's approval wait. Schwab says most product-access
> requests are reviewed within two business days, although some take longer.

## Before you start

You need:

- a Schwab brokerage account;
- Windows 10 or 11;
- [Python 3.12, 3.13, or 3.14](https://www.python.org/downloads/windows/);
- this repository downloaded and extracted to a normal folder; and
- a browser for the Schwab authorization step.

If you installed Python from python.org, leave the Python Launcher option enabled. Incoooming's
setup script uses the `py` command.

On this repository's GitHub page, select **Code**, then **Download ZIP**. Open the downloaded ZIP,
select **Extract all**, and work from the extracted folder—not from inside the ZIP.

Run one command block at a time and wait for the PowerShell prompt to return. Nibwick is sturdy;
two setup commands fighting in one terminal are not.

## 1. Become an Individual Developer

1. Open the [Schwab Developer Portal](https://developer.schwab.com/).
2. Select **Register**. Verify your email and sign in.
3. On the welcome page, find **Individual Developer** and select **Continue**.
4. If you already had a portal account, open **Profile** and select
   **Add Individual Developer Role** instead.

Schwab requires this role for the personal Trader API. It also requires an existing Schwab
brokerage account.

## 2. Request Trader API access

1. Open [API Products](https://developer.schwab.com/products).
2. Choose **Individual Developers**.
3. Open **Trader API - Individual**.
4. Select **Request Access** and submit the form.
5. Wait until the request is approved.

This is Schwab's personal-use product. Do not choose **Trader API - Commercial** for a local copy
connected only to your own account.

Nibwick's useful contribution here: the waiting screen is not broken. Schwab reviews the request.

## 3. Create the Schwab app

After the product-access request is approved:

1. Open the [Apps dashboard](https://developer.schwab.com/dashboard/apps).
2. Select **Create App**.
3. Select both products shown under Trader API - Individual:
   - **Accounts and Trading Production**
   - **Market Data Production**
4. Enter `0` for **Order Limit**. Incoooming does not place trades.
5. Give the app a recognizable name, such as `Incoooming`.
6. You may use this description:

   ```text
   Private, local, read-only analytics for my Schwab portfolio, positions, options, transactions, dividends, and market data.
   ```

7. Enter this callback URL **exactly**:

   ```text
   https://127.0.0.1:8182/
   ```

8. Create the app. Do not continue until its status is **Ready For Use** or **Active**.
9. Open **App Details** and copy the **Client ID** and **Client Secret** somewhere private for the
   next step.

The callback must match character for character later. `https`, port `8182`, and the final `/` all
matter.

## 4. Put the three app values in Incoooming

Open the extracted project folder in File Explorer. Click the address bar, type `powershell`, and
press Enter. The PowerShell prompt should end with the name of the project folder.

Run:

```powershell
.\scripts\bootstrap.cmd
Copy-Item .env.example .env
notepad .env
```

Notepad will open the local settings file. Nibwick's translation table:

| Schwab calls it | Incoooming calls it |
| --- | --- |
| Client ID | `SCHWAB_APP_KEY` |
| Client Secret | `SCHWAB_APP_SECRET` |
| Callback URL | `SCHWAB_CALLBACK_URL` |

The first three lines should look like this after you paste your values:

```text
SCHWAB_APP_KEY=paste-your-client-id-here
SCHWAB_APP_SECRET=paste-your-client-secret-here
SCHWAB_CALLBACK_URL=https://127.0.0.1:8182/
```

Do not add quotation marks or spaces around the values. Save the file and close Notepad.

Check the setup without printing either secret:

```powershell
.\.venv\Scripts\schwab-dashboard.exe doctor
```

You should see `Schwab credentials configured: True`. A missing token is normal at this point.

## 5. Authorize Schwab and build the first book

First, prepare the local database and ask Incoooming for a Schwab authorization link:

```powershell
.\.venv\Scripts\schwab-dashboard.exe db-upgrade
.\.venv\Scripts\schwab-dashboard.exe auth-url
```

Copy the long URL printed by `auth-url` and open it in your browser. Sign in on Schwab's page,
choose the accounts you want to share, and approve the connection.

Schwab will send the browser to an address beginning with:

```text
https://127.0.0.1:8182/?code=...
```

The browser may show `This site can't provide a secure connection`. That is expected during this
manual local setup. **Do not reload the page.** Copy the entire URL from the browser's address bar.

Back in PowerShell, run:

```powershell
.\.venv\Scripts\schwab-dashboard.exe auth-complete
```

When it asks for the callback URL, paste **once** and press Enter. The pasted text stays invisible
because it contains a one-time authorization code.

After PowerShell says `Authorization stored`, check the connection and run the first sync:

```powershell
.\.venv\Scripts\schwab-dashboard.exe doctor
.\.venv\Scripts\schwab-dashboard.exe sync
.\scripts\run-local.cmd
```

Leave that PowerShell window open. Visit [http://127.0.0.1:8182/](http://127.0.0.1:8182/), choose
**Schwab live**, and select **Get Incoooming**.

You are connected when `doctor` reports a stored token, `sync` finishes successfully, and the desk
shows **SCHWAB LIVE** with a recent sync time.

## Next time you use it

After restarting the computer, open PowerShell in the project folder and run only:

```powershell
.\scripts\run-local.cmd
```

You do not recreate the Schwab app or rewrite `.env`. Incoooming keeps the OAuth token in Windows
Credential Manager and refreshes normal access tokens automatically. If the desk specifically says
**Reconnect Schwab**, repeat the `auth-url` and `auth-complete` steps with a fresh authorization.

Press `Ctrl+C` in the server window when you want to stop Incoooming.

## If something goes wrong

### `Schwab credentials configured: False`

Make sure the file is named `.env`, lives in the project folder, and contains nonblank values for
`SCHWAB_APP_KEY` and `SCHWAB_APP_SECRET`.

### Schwab rejects the callback or token request

Compare the app's registered callback with `.env`. They must both be exactly:

```text
https://127.0.0.1:8182/
```

An authorization code is short-lived and can be used only once. Run `auth-url` again, finish the
Schwab approval again, copy the new callback URL, and paste it once into `auth-complete`.

### The callback page is white or shows an SSL error

That page does not need to load. Copy its entire address and give it to `auth-complete`.

### PowerShell shows `WinError 10048`

Port `8182` is already in use, usually because Incoooming is already running. Check
[http://127.0.0.1:8182/](http://127.0.0.1:8182/) before starting a second server. If the page works,
use the existing server window.

### The desk opens but has no current positions

Keep the server open and select **SYNC NOW**, or stop the server with `Ctrl+C` and run:

```powershell
.\.venv\Scripts\schwab-dashboard.exe sync
.\scripts\run-local.cmd
```

### You changed the Schwab password, two-factor setup, or authorized accounts

Schwab may require a fresh consent flow. Run `auth-url`, approve the connection, and complete it
with the new callback URL.

## Keep the keys inside the house

- Never post the Client ID, Client Secret, callback code, `.env`, or brokerage exports in a GitHub
  issue, screenshot, or chat.
- Never commit `.env` or the `var` directory. This repository already ignores both.
- Incoooming stores OAuth tokens in Windows Credential Manager, not in the repository.
- Incoooming does not ask for a Schwab username or password and does not implement trading
  endpoints.

## Official Schwab links

- [Developer Portal](https://developer.schwab.com/)
- [Register](https://developer.schwab.com/register)
- [API Products](https://developer.schwab.com/products)
- [Apps dashboard](https://developer.schwab.com/dashboard/apps)
- [User Guides](https://developer.schwab.com/user-guides)
- [Trader API - Individual](https://developer.schwab.com/products/trader-api--individual)

Last checked against Schwab's portal on August 12, 2026. Portal labels and approval timing can
change; Schwab's pages are the authority when they differ from this guide.
