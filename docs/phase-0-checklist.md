# Original Incoooming Schwab access checklist

This was the original live-connect evidence list. Incoooming now runs that approved read-only Schwab
adapter locally. Keep the checklist as the access recipe; the software title is Incoooming, and the
CLI is still invoked as `schwab-dashboard`.

## Developer access

- [ ] Schwab developer account created.
- [ ] Individual Trader API app status is ready for use.
- [ ] Exact callback URL recorded.
- [ ] App key and secret saved only in local `.env` or a secret manager.
- [ ] Manual OAuth flow completes.
- [ ] Token refresh succeeds once.

## Capability probes

- [ ] Account-number/hash endpoint returns the expected accounts.
- [ ] Accounts-with-positions response is saved as a raw event.
- [ ] Stock and option positions both map successfully.
- [ ] No visible account number appears in application logs.
- [ ] A second sync is stored as a new observation without duplicating rows inside the same run.
- [ ] A deliberately expired access token refreshes or fails with a clear re-authentication message.

## Representative history for the next slice

Export or identify examples of sell-to-open, buy-to-close, expiration, assignment, roll, partial fill, stock trade, dividend, fee, and deposit/withdrawal. Sanitize account identifiers before using a record as a test fixture.

## Exit evidence

- `schwab-dashboard doctor` reports database, credentials, and token status.
- `schwab-dashboard sync` completes against the real account.
- Incoooming lists account masks and current position quantities.
- The latest sync has zero unresolved structural reconciliation errors.
