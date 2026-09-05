# Get Incoooming running on your Mac

Start with the demo, then choose CSV files or connect your own Schwab account. The app runs on
your Mac and opens in your browser. It never places trades.

**Tested on macOS 15, on both Apple Silicon and Intel**, with Python 3.12, 3.13, and 3.14.
Native checks cover setup, restarts, Keychain, the Safari interface, and CSV imports in Chrome.
See [the results and exact versions](platforms/macos-validation.md). Safari CSV imports, other
macOS versions, and iPhone/iPad aren't part of this verified setup.

## 1. Get Python and the project

Use [Google Chrome](https://www.google.com/chrome/) if you plan to import CSV files. Safari can
display the demo and charts, but its CSV file-selection flow has not been verified. You don't
need to change your default browser; just open Incoooming's local address in Chrome.

Install Python 3.12, 3.13, or 3.14 from [python.org](https://www.python.org/downloads/macos/).
Choose the standard macOS installer. It supports both Apple Silicon and Intel. After installation,
open its folder under Applications and run **Install Certificates.command** to finish HTTPS
certificate setup. [Python's installation guide](https://docs.python.org/3.14/using/mac.html)
shows these steps. Leave Apple's system Python alone.

If you already have a supported Python installed, you can use it. Open a new Terminal window and
check `python3 --version`. Setup uses a supported interpreter on your PATH and creates the app's
own `.venv` for its packages.

Download the repository with GitHub's **Code → Download ZIP**, then double-click the ZIP to
extract it. In Terminal, type `cd ` (including the space), drag the extracted project folder from
Finder into the Terminal window, and press Enter. The folder should contain `README.md` and
`scripts`.

Git users can clone instead:

```sh
git clone https://github.com/ehwwpk/incoooming-unofficial-desk.git
cd incoooming-unofficial-desk
```

## 2. Start the demo

Run these commands one at a time. Wait for setup to finish successfully before starting the app:

```sh
sh ./scripts/bootstrap.sh
sh ./scripts/run-demo.sh
```

Open **[http://127.0.0.1:8182](http://127.0.0.1:8182)** in Safari or your preferred browser. If
the welcome page appears, click **OPEN DEMO**. The Desk shows **SIM** and a fixed August 7, 2026
date. **Results** has the four benchmark lines; **Options** includes calls, puts, and rolls.

Leave Terminal open while using the app. Press **Control+C** in that Terminal window to stop it.
No brokerage account, `.env` file, or login is needed for the fictional demo.

## Import CSV files

Stop the standalone demo with Control+C first, then run:

```sh
sh ./scripts/run-local.sh
```

Open the local address in **Chrome**, choose **BOOK → Import CSV**, select your broker and files, then preview
them. Check skipped rows and their reasons before importing. For a practice import, choose
**Generic / template** and use both fictional files in [`examples/csv`](../examples/csv).

You don't need API credentials. CSV exports provide different amounts of information; activity
alone doesn't establish your current holdings. They don't supply live chains, Greeks, or daily
account history for the full benchmark chart. See the [supported CSV formats](systems/csv-import.md).

## Connect Schwab

You need your own approved Schwab Individual Trader API app. Request access and create the app
using [steps 1 and 2 of the Schwab guide](getting-started-schwab.md#1-request-individual-trader-api-access).
Register the exact callback `https://127.0.0.1:8182/`. Schwab controls approval and market-data
access. You can use demo or CSV mode while you wait.

Stop any running Incoooming server with Control+C. From the project folder in Terminal, create
a settings file if you don't already have one, then open it:

```sh
[ -f .env ] || cp .env.example .env
open -e .env
```

Fill in your own `SCHWAB_APP_KEY` and `SCHWAB_APP_SECRET`, leave the callback matching the registered
value, and save. Keep the file private. Then run:

```sh
sh ./scripts/connect-schwab.sh
```

The helper opens Schwab in your browser. Sign in there and choose the accounts to share.
The final callback page may show a connection error; that's expected because the callback isn't
a hosted page. Press **Command+L**, then **Command+C** to copy its whole address. Return to the
waiting Terminal prompt, paste with **Command+V**, and press Enter. The paste is hidden because
the URL contains a one-time code. Keep it out of chat, shell commands, screenshots, and issues.

macOS may ask whether this Python installation can access the saved login in Keychain. Review
the request and allow access if you want this installation to save/reuse the login. Tokens are
stored in **macOS Keychain**, with no plaintext token fallback. After authorization, the helper
syncs the account and starts the app. Choose **Schwab live** under BOOK and check for a recent
successful sync time.

If the browser doesn't open automatically, use the link printed in Terminal. If no link appears,
press Control+C and run `sh ./scripts/connect-schwab.sh --no-browser` to get one. Control+C also
cancels the helper. If a code expires or has already been used, run the helper again to start a
fresh login. A saved token alone doesn't prove that an account sync succeeded.

The automated Mac checks use fictional data, mocked broker responses, and dummy Keychain entries.
They do not log in to a real Schwab account. Your developer approval, account permissions, and
market-data access still determine whether a real connection succeeds.

## Start, stop, and reconnect

| What you want | Terminal command |
| --- | --- |
| Demo | `sh ./scripts/run-demo.sh` |
| Your CSV files or connected account | `sh ./scripts/run-local.sh` |
| Stop or restart | Control+C in the server Terminal, then run the same command again |
| Reconnect Schwab | Stop the server first, then run `sh ./scripts/connect-schwab.sh` |
| Check setup without printing secrets | `.venv/bin/schwab-dashboard doctor` |
| Remove the saved Schwab login | `.venv/bin/schwab-dashboard auth-clear` |

Keep the app local. It doesn't install a background service. Closing the server Terminal stops
the app; closing a browser tab doesn't. With a saved Schwab connection, the normal app refreshes
after startup and every 15 minutes by default. You can change or disable automatic refresh in
`.env`. Imported books and stored data remain available after restarting.

After getting a project update, stop the app, rerun `sh ./scripts/bootstrap.sh`, and start it again.
Database updates run automatically when the server starts. Keep a private backup of `.env` and
`var` before updating an installation you rely on. If you chose a different data directory in
`SCHWAB_DASHBOARD_DATA_DIR`, back up that directory instead of `var`.

## If setup gets stuck

**Python isn't found or is too old:** install a supported version, then open a new Terminal.
If several versions coexist, you can select one explicitly with
`INCOOOMING_PYTHON=python3.14 sh ./scripts/bootstrap.sh` when creating a new `.venv`.
Setup reuses an existing supported environment and prints its Python version; that setting
doesn't replace or upgrade the environment's interpreter.

**An existing `.venv` is unusable:** Python environments don't transfer between Windows and Mac.
Use a fresh project folder to create a Mac environment. Keep your old folder until you've
preserved any private settings/data you need. Setup won't delete that environment for you.

**Certificate errors:** complete Python's **Install Certificates.command** step. Check the Mac's
clock and network connection. Don't disable HTTPS certificate verification.

**The port is already in use:** check for another Incoooming Terminal and stop it with Control+C.
The Mac launcher leaves other processes alone. If a different app uses the port, select a free
`SCHWAB_DASHBOARD_PORT` in `.env`; the server prints the correct browser address. The registered
Schwab callback must continue to match `SCHWAB_CALLBACK_URL` exactly.

**Keychain access is denied or the login is damaged:** unlock your login keychain using macOS
Keychain Access and retry. Review its access permission for the Python installation you're using.
The app shows a saved-login warning and keeps local CSV use available. If the saved token is
damaged, stop the app, run `.venv/bin/schwab-dashboard auth-clear`, and reconnect. If clearing fails,
it has not been confirmed removed; resolve the Keychain permission and retry.

**The app still shows fictional data:** stop `run-demo.sh` and start `run-local.sh`, then choose
your book under BOOK.

**A CSV file can't be read:** make sure the file has finished downloading to your Mac, then
choose it again in Chrome. Preview the files before importing. Safari CSV uploads are not part
of the verified Mac setup.

Want your coding agent to help? Use the [setup prompt in the README](../README.md#want-your-coding-agent-to-help).
Share error messages with private details removed. Keep credentials, callbacks, exports, and
database files out of chats and public issues.
