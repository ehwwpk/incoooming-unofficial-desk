# macOS support: implementation and acceptance plan

This plan was completed before implementation. The aim is a supported local Mac release with
repeatable native test evidence, without requiring the owner to own or manually test a Mac.

## Scope

Keep the existing Python server, local SQLite data, calculations, and browser interface. Add
Terminal setup/start/connect helpers for macOS and test on Apple Silicon and Intel. Windows
support and its Python 3.12–3.14 checks remain in place. No native `.app`, installer, background
service, remote hosting, or iPhone/iPad support is included in this change.

The initial native validation target is macOS 15 on both architectures with Python 3.12, 3.13,
and 3.14. Support documentation will identify the actual successful configurations and link the
workflow evidence. It must not call the implementation tested before those runs pass.

## Implementation order

1. Add portable `/bin/sh` bootstrap, demo, normal-server, verify, and Schwab connection helpers.
   They enter the repository directory before reading settings, quote paths, and use LF endings.
   Bootstrap uses a supported Python selected explicitly or from PATH, installs inside `.venv`,
   and preserves existing settings/data. Broken or foreign-platform environments produce an
   actionable error rather than being removed automatically. No system Python changes or sudo
   package installation are needed.
2. Add a shared launch preflight for the configured IPv4 loopback port. An occupied port causes
   a clear refusal before database migration; no listener is killed. The app runs in the
   foreground and stops with Ctrl+C. The implementation retains the reserved socket and passes
   it to Uvicorn, so another process cannot take the port between the check and startup.
   Demo keeps its separate database and never initializes brokerage authorization or auto-sync.
3. Add a portable guided OAuth command using the existing callback validation and token exchange.
   It opens the normal browser or prints the authorization URL as a fallback, then accepts the
   callback through a hidden Terminal prompt. It never polls the clipboard, starts an HTTPS
   listener, puts a callback in shell history, or prints token/secret payloads. Cancellation and
   failure stop the flow. The default successful path performs one initial read-only sync;
   the Mac wrapper starts the normal server afterward.
4. Harden credential storage. Missing, disabled, denied, locked, or corrupt storage should give
   a sanitized actionable message; it should not prevent the demo/CSV interface from loading.
   Failed writes must not claim success. Logout must distinguish an already-absent token from
   a failed deletion. No plaintext token fallback is permitted. Background readiness checks
   should recover if Keychain becomes accessible later.
5. Update README, agent setup prompt, guides, CLI help, and in-app setup/recovery instructions
   for both operating systems. Document Python installation, certificate setup where applicable,
   command locations, closing/reopening Terminal, source switching, and Keychain permission
   recovery. Default browser URL remains HTTP loopback; the Schwab callback remains the exact
   configured HTTPS address.
6. Validate locally, push the reviewed changes to a `codex/` validation branch, run native hosted
   Mac checks, inspect artifacts/logs, fix failures, and repeat the affected checks. Update the
   support wording only after successful native evidence exists. Do not publish a release or
   change the repository's default branch as part of validation.

## Required evidence

| Area | Acceptance check |
| --- | --- |
| Core behavior | Full unit/integration suite, lint, types, security checks, and wheel build on the supported matrix; existing Windows checks retained |
| Installation | Native architecture and Python version recorded; fresh wheel/environment; imported module comes from that environment; packaged migrations and assets work outside the checkout |
| Launchers | Actual `/bin/sh` execution from outside a path containing spaces; explicit interpreter selection; valid/broken/foreign environments; stable settings/data paths; no hidden environment deletion |
| Server lifecycle | Real listener and health response; demo/normal modes; occupied unrelated port remains untouched; SIGINT shutdown releases the port; subsequent startup works; user settings/data persist |
| Demo isolation | No live ledger or broker access; wrong-source imports rejected; source switching on a normal server remains usable |
| Credentials | Real native macOS Keychain backend saves, reloads in a fresh process, updates, deletes, and reports absence for unique dummy credentials; exact created items cleaned up |
| Storage failures | Injected denied/locked/unavailable/corrupt failures produce useful redacted errors; normal CSV startup survives; failed save/logout cannot report success |
| OAuth | Existing validation/refresh cases plus browser fallback, hidden prompt, cancellation, failed callback, and storage failure; all broker network responses mocked |
| Safari | Native Safari WebDriver on both Mac architectures opens the source gateway, demo Desk, four benchmark lines/period switch, Risk Lens, Roll Board → Radar, and CSV preview/import; screenshots and result metadata saved |
| Publication claim | README states the measured platform coverage and keeps real broker authorization separate from mocked OAuth/native Keychain checks |

The keyring library's current macOS backend ignores the alternate-keychain-path setting. Native
tests therefore use unique dummy service/account names on an ephemeral hosted runner and clean
up only those entries. They do not access the user's credentials or intentionally provoke an
unattended Keychain permission dialog. Denied/locked behavior is covered by deterministic tests.

Safari means Apple's actual browser, not Playwright WebKit. Browser automation is a checked-in
application regression test running on the ephemeral Mac. All screenshots and test books use
fictional data. Record OS, architecture, Python, Safari, commit, and gate outcomes without logging
credential payloads.

## Edge cases and limits

- Repository paths may contain spaces. The working directory used to launch a helper must not
  change the selected `.env` or relative data directory.
- A supported Python may coexist with Apple's system Python and other project environments.
  Helpers must not modify those installations or silently select a different CI interpreter.
- Existing Windows `.venv` directories cannot be reused on a Mac; instructions must preserve
  `.env` and `var` while explaining how to create a separate local environment.
- Network/package failures, unsupported Python, full disks, missing permissions, port races,
  invalid settings, and interrupted bootstrap/start/login must fail clearly without success
  messages or damage to existing settings/data.
- Native credential writes may fail after the backend has removed an older item. Recovery can
  require reconnecting; do not promise that the old token survives every storage failure.
- File-picker behavior, chart rendering, browser storage, zoom/Retina layout, and window links
  need native Safari checks rather than assuming that HTTP route tests prove the UI works.
- Hosted tests do not authorize a real Schwab account, establish developer approval/entitlements,
  certify all macOS versions, or constitute an App Store/notarized application review.

## Sources used for planning

- [GitHub hosted Mac architectures and runner labels](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Python on macOS](https://docs.python.org/3.14/using/mac.html)
- [Keyring backends and macOS support](https://keyring.readthedocs.io/en/stable/)
- [Apple Safari WebDriver setup](https://developer.apple.com/documentation/safari-developer-tools/macos-enabling-webdriver)
