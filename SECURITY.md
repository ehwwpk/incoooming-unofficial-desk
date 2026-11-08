# Security policy

## Supported version

Security fixes are applied to the current `main` branch. After updating, stop the app and rerun
bootstrap to refresh dependencies, then restart it. Back up your local settings and data privately
before updating; older checkouts and environments do not receive fixes automatically.
CI checks dependency advisories on code changes and on a weekly schedule. Dependabot also checks
for updates. Passing scans are useful checks, not a guarantee that every vulnerability is known.

## Report a vulnerability

Do not open a public issue with a vulnerability, token, account identifier, statement, or broker
payload. [Report a vulnerability privately on GitHub](https://github.com/ehwwpk/incoooming-unofficial-desk/security/advisories/new).
If that feature is unavailable, contact the repository owner through their public GitHub profile
without including sensitive data in the first message.

Include the affected version, a short reproduction, and the impact. Replace account data, OAuth
codes, tokens, app credentials, and financial values with clearly fake examples.

## Local security model

Incoooming is designed for one user on one computer. The server accepts IPv4 loopback hosts
only and is not hardened for LAN or internet exposure. OAuth tokens use the operating system's
credential store: Windows Credential Manager or macOS Keychain. No plaintext token fallback is used.
The app rejects replacement keyring backends on those platforms. This does not protect against
malware or another program already running as you on the same computer.
Local SQLite databases, `.env` files, broker exports, logs, and screenshots can still contain
sensitive financial information; they are not encrypted by the app. Keep them out of commits and
public reports. Use your operating system's account and disk protections for local files and backups.

The Schwab integration reads account and market data. It does not implement order entry.
