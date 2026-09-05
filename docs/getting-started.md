# Get Incoooming running

This guide uses Windows commands. **On a Mac, use [the Mac setup guide](getting-started-macos.md).**

Start with the demo to see the app working. Then choose CSV files or a Schwab connection for your
own data. You can do the first part without a brokerage account or any API credentials.

If you'd like a coding agent to handle setup, open the project folder in your agent and use the
[copyable setup prompt in the README](../README.md#want-your-coding-agent-to-help).

## 1. Get Python and the project

These instructions are for Windows 10 or 11, with Python 3.12, 3.13, or 3.14.
Linux setup isn't covered by this beta.

If you need Python, install a supported version from
[Python's Windows downloads](https://www.python.org/downloads/windows/). Keep the Python launcher
enabled if the installer offers it, then open a new terminal after installation. Setup can use
either a supported `py` installation or a supported `python` command.

On the GitHub repository page, choose **Code → Download ZIP**. Right-click the downloaded ZIP,
choose **Extract All**, and open the extracted folder. You want the folder containing `README.md`,
`pyproject.toml`, and `scripts`.

If you already use Git, you can clone instead:

```powershell
git clone https://github.com/ehwwpk/incoooming-unofficial-desk.git
cd incoooming-unofficial-desk
```

## 2. Install and start the demo

In File Explorer, open that project folder. Click the address bar, type `powershell`, and press
Enter. Run:

```powershell
.\scripts\bootstrap.cmd
```

Setup creates a `.venv` folder for the app's Python packages. It needs internet access to download
them. Wait for **Bootstrap complete**; if there is an error, resolve it before continuing.

Then run:

```powershell
.\scripts\run-demo.cmd
```

Open **[http://127.0.0.1:8182](http://127.0.0.1:8182)** in your browser. The terminal stays open
while the demo runs. If you see the welcome page, click **OPEN DEMO**. The Desk will show a **SIM**
notice and an August 7, 2026 date. Open **Results** to see the four comparison lines, then
**Options** to explore calls, puts, and rolls.

All demo positions, prices, returns, and model inputs are fictional. No `.env` file or brokerage
login is needed. The demo has its own database; its Radar settings reset when the server restarts.

## 3. Choose your own data

**First stop the standalone demo:** click its terminal and press `Ctrl+C`.
The standalone demo always shows fictional data, so use the normal launcher for your own book.

### Import your own CSV files

Run:

```powershell
.\scripts\run-local.cmd
```

Open the local address above and choose **BOOK → Import CSV**. Pick the broker, give the book a
name, and choose your files. Preview them, check any skipped rows and their reasons, then import.
Different imports stay in separate books.

For a practice import, choose **Generic / template** and use both files in
[`examples/csv`](../examples/csv). They contain made-up data.

| Broker or format | Files to use |
| --- | --- |
| Schwab | Supported web/StreetSmart positions and transaction CSVs; avoid lot-detail exports |
| Fidelity | Supported web positions and compatible account-activity CSVs |
| Robinhood | Custom account-activity CSV, rather than a PDF statement |
| Webull | Order history with executed quantities; it does not provide current positions or cash balance |
| IBKR | Activity Statement CSV with supported Trades, Open Positions, or Cash Transactions sections; Flex/XML/PDF formats aren't supported |
| Generic / template | The Incoooming position and activity templates |

You can choose up to eight files, each up to 10 MB. Positions help show what you hold; activity
helps explain how you got there. The preview tells you what the app recognizes. If it can't safely
read a row, that row stays out of the import.

CSV imports have fewer inputs than a connected account. They don't supply live quotes, option
chains, Greeks, IV, tax lots, or a daily account history. Some views will have gaps; a missing
number doesn't mean zero. The date at the top of a CSV book is the local import date, while dated
activity keeps its own dates.

For exact supported columns and limitations, see the [CSV format reference](systems/csv-import.md).
If your export isn't recognized, report the broker and column names using a made-up example.
Keep the real financial file private.

### Connect Schwab

Follow [Connect Schwab on Windows](getting-started-schwab.md). You'll need your own approved
Individual Trader API app. The guide walks through the app settings, your local `.env` file, and
the login flow. Incoooming reads account and market data; it has no order-placement workflow.

An agent can help install and check the local app, but Schwab controls approval and access. You
complete broker login and enter secrets privately. A successful sync and a recent sync time in
the app confirm the connection is working.

## Start it next time

Open PowerShell in the project folder and run the command for the book you want:

| What you want | Command |
| --- | --- |
| Fictional demo | `.\scripts\run-demo.cmd` |
| Your imported files or connected Schwab account | `.\scripts\run-local.cmd` |
| Restart the normal app after a code update | `.\scripts\restart-local.cmd` |
| Reconnect when Schwab authorization expires | `.\scripts\connect-schwab.cmd` |

You don't need to run bootstrap every time. Run it again after getting a project update so any
new packages are installed. The launcher updates the local database when needed.

## If something gets stuck

**“Python not found” or an unsupported version:** install Python 3.12–3.14, open a new PowerShell
window, and run bootstrap again. You can check an installation with `py -3.12 --version` (change
the version if needed) or `python --version`.

**“scripts\bootstrap.cmd” isn't found:** you're probably in the ZIP or the wrong folder. Extract
the download and open PowerShell in the folder containing `README.md` and `scripts`.

**PowerShell says scripts are disabled:** use the supplied `.cmd` commands shown above. You don't
need to run the `.ps1` files directly or change the machine's execution policy.

**The browser can't connect:** check the terminal for an error and confirm it is still running.
Use `http://127.0.0.1:8182`, with `http`, for the app. The `https` address in the Schwab guide is
only the login callback.

**Port 8182 is already in use, or you still see the demo:** check for another open Incoooming
terminal and stop the demo with `Ctrl+C`. Start `run-local.cmd` for your own data. If the normal app
is already running, `restart-local.cmd` can restart it; the launcher checks the app's identity
before stopping a process.

**A number is missing:** check that you selected the intended book under **BOOK**, then check the
import preview or data-health details. An activity-only CSV and a connected account provide
different amounts of information.

For help, share the command you ran, your Python version, the selected book type, and an error
message with private details removed. Keep `.env`, broker files, databases, tokens, and callback
URLs out of chats and public issues.
