# Contributing

Thanks for helping improve Incoooming. This is a beta, so small, testable changes are
easier to review than broad rewrites.

## Before opening an issue

- Search existing issues.
- Do not include real account data, OAuth URLs or codes, tokens, app credentials, statements, or
  screenshots with financial details.
- State whether the problem affects Schwab live data, a CSV import, or the fictional demo.
- Include the command you ran and a sanitized error message.

Use the private process in [SECURITY.md](SECURITY.md) for vulnerabilities.

## Development setup

Install Python 3.12, 3.13, or 3.14 and Node.js, then run:

```powershell
.\scripts\bootstrap.cmd
```

On a Mac, use `sh ./scripts/bootstrap.sh` instead. The [Mac setup guide](docs/getting-started-macos.md)
walks through Python installation and starting the app. Run `sh ./scripts/verify.sh` for lint,
formatting, type checks, and tests. For the Python commands below, on a Mac replace
`.\.venv\Scripts\python.exe` with `./.venv/bin/python`.

Before submitting a pull request:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pip_audit --local --skip-editable --progress-spinner off
.\.venv\Scripts\python.exe -m bandit -r src -q -s B101,B105
.\.venv\Scripts\python.exe -m pytest --cov=schwab_dashboard --cov-fail-under=80
Get-ChildItem src/schwab_dashboard/web/static -Filter *.js -Recurse |
  ForEach-Object { node --check $_.FullName }
```

The last command above uses PowerShell. To check JavaScript in Mac Terminal, use:

```sh
find src/schwab_dashboard/web/static -type f -name '*.js' -print0 | xargs -0 -n 1 node --check
```

Add tests for accounting, parser, and reconciliation changes. Use `Decimal` for money and
quantities. Preserve raw source data and keep missing values distinct from zero. Browser routes
must not call a broker directly.

## Pull requests

Explain the user-visible change, the evidence behind any accounting rule, and the checks you ran.
Use fictional fixtures. If a broker payload shape is important, remove identifiers and amounts or
build a minimal synthetic payload instead of committing a live response.

Changes to setup, login storage, or browser behavior should pass both Windows and Mac CI. Mac
checks include Intel and Apple Silicon, native Keychain storage with disposable dummy tokens,
the Safari interface, and Chrome with real CSV files. Safari CSV file selection remains
unverified because the native automation cannot read selected files. Keep support claims tied
to those results; automated checks do not prove a real broker login was completed on a Mac.
