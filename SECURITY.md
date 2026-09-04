# Security policy

## Supported version

Security fixes are applied to the current `main` branch during the beta.

## Report a vulnerability

Do not open a public issue with a vulnerability, token, account identifier, statement, or broker
payload. Use GitHub's private vulnerability reporting feature for this repository. If that feature
is unavailable, contact the repository owner through their public GitHub profile without including
sensitive data in the first message.

Include the affected version, a short reproduction, and the impact. Replace account data, OAuth
codes, tokens, app credentials, and financial values with clearly fake examples.

## Local security model

Incoooming is designed for one user on one Windows computer. The server accepts IPv4 loopback hosts
only and is not hardened for LAN or internet exposure. OAuth tokens use Windows Credential Manager.
Local SQLite databases, `.env` files, broker exports, logs, and screenshots can still contain
sensitive financial information; keep them out of commits and public reports.

The Schwab integration reads account and market data. It does not implement order entry.
