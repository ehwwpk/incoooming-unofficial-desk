# CSV import contract

## Usable slice

The source gateway accepts up to eight UTF-8 CSV files per import and 10 MB per file. Positions and
activity exports may be uploaded together. Each submission creates a new named book with:

- user-supplied source label and creation time;
- file names, SHA-256 hashes, detected kind, headers, and row counts;
- raw row values;
- normalized position, execution, cash-movement, and lifecycle records;
- rejected-row counts and bounded warnings.

The parser detects files from required columns rather than trusting the filename. Activity detection
runs before positions detection because activity exports commonly contain symbol, quantity, and
price columns too. Duplicate files in one submission fail with a plain-language error.

## Truth and limitations

- Exported P/L is accepted only from an explicit P/L column. It is not manufactured from ambiguous
  broker cost-basis signs.
- Missing cash balances, tax lots, quotes, Greeks, IV, price history, and corporate-event context
  remain unavailable.
- A positions-only book can show current inventory and obligations but not historical income.
- An activity-only book is marked partial because current coverage cannot be established.
- Unknown file shapes fail closed and point the user to downloadable generic templates.
- The source selector records provenance and changes the displayed book label. It does **not** change
  parsing behavior today: Schwab, Fidelity, Robinhood, and Generic all enter the same
  column-detected importer. The parser API intentionally has no broker argument so this limitation
  cannot be mistaken for broker-specific normalization in code.
- Sanitized real exports and regression fixtures are required before a broker-specific format
  profile can be promoted to certified support. When those profiles exist, the stored source label
  will select the corresponding profile and preserve the generic detector as an explicit fallback.

## Supported generic templates

The gateway provides separate positions and activity templates. Common header aliases are accepted
for account, symbol, description, quantity, mark, market value, cost, P/L, date, action, price,
fees, and cash amount. OCC option symbols are parsed directly; a bounded plain-description parser is
the fallback.

CSV books are read-only. Importing a corrected export creates another book, preserving the prior
evidence rather than mutating it in place.

## Official export references

- [Schwab StreetSmart Edge manual](https://help.streetsmart.schwab.com/edge/printablemanuals/edgemanual.pdf)
  documents CSV exports for positions and transactions.
- [Fidelity Portfolio Positions help](https://www.fidelity.com/webxpress/help/topics/learn_portfolio_positions.shtml)
  documents downloading position information as CSV.
- [Robinhood account documents help](https://robinhood.com/us/en/support/articles/finding-your-account-documents/)
  documents custom account-activity reports delivered as CSV.

These references establish that an export path exists; they do not establish one permanent header
schema. The importer therefore detects supported columns and keeps any mismatch visible.
