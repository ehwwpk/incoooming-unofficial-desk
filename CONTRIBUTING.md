# Contributing

Thanks for helping improve Incoooming. This is a Windows-first beta, so small, testable changes are
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

Add tests for accounting, parser, and reconciliation changes. Use `Decimal` for money and
quantities. Preserve raw source data and keep missing values distinct from zero. Browser routes
must not call a broker directly.

## Pull requests

Explain the user-visible change, the evidence behind any accounting rule, and the checks you ran.
Use fictional fixtures. If a broker payload shape is important, remove identifiers and amounts or
build a minimal synthetic payload instead of committing a live response.
