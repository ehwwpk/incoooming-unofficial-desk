# Incoooming CSV import contract

## Usable slice

Incoooming's source gateway accepts up to eight UTF-8, UTF-16, or Windows-1252 CSV files per import
and 10 MB per file. Positions and activity exports may be uploaded together. Every import must pass a
preview before commit. The preview shows:

- detected broker profile, confidence, encoding, delimiter, and header row;
- positions and activity that will enter the book;
- ignored, needs-review, and rejected row counts;
- the capabilities actually present in the selected files;
- warnings, including a selected-broker/file-shape mismatch.

Every stored book keeps file names, SHA-256 hashes, raw rows, source row numbers, row dispositions,
reasons, stable normalized fingerprints, and the accepted position, execution, cash-movement, and
lifecycle records. Exact duplicate files fail. Overlapping normalized records across different
selected files are ignored with a reason.

## Format adapters

The broker choice is operational, not a label. The importer currently recognizes:

- Schwab web position and transaction exports, including preamble rows;
- Fidelity web positions and activity, including compact option symbols;
- Robinhood account activity;
- Webull filled-order history;
- IBKR multi-section Activity Statements (`Trades`, `Open Positions`, and `Cash Transactions`);
- Incoooming's generic position and activity templates.

Synthetic golden fixtures exercise each adapter. Broker portals can change exports, so preview
remains mandatory. Webull order history supplies executions, not positions or cash. Non-filled
orders are ignored. IBKR Flex/custom statements vary; only recognized sections are normalized.

## Truth rules

- Exported P/L is accepted only from an explicit P/L column.
- Transfers and deposits are external cash flow, never option or dividend income.
- Dividends, interest, fees, withholding, and transfers remain separate movement types.
- Standard options may use an explicit exported multiplier or a visible `assumed_standard` 100x
  multiplier.
- An adjusted/non-standard option without an explicit multiplier is held for review. It is never
  silently forced to 100x.
- Unknown cash actions and unsafe option rows stay out of the ledger.
- Positions-only books cannot manufacture historical income. Activity-only books cannot establish
  current coverage.
- CSV capabilities are evidence-based. Balances, lots, Greeks, IV, price history, and live marks
  remain unavailable unless a separate provider supplies them.

CSV books are read-only. Importing a corrected export creates another book, preserving the prior
evidence rather than mutating it in place.

## Market-data boundary

CSV import builds the position/history ledger only. A later market-data provider may enrich a CSV
book with quotes, option chains, Greeks, IV, dividends, and bars, but that adapter must remain
separate. Missing or weak market data must never alter imported cash or executions.

## Official export references

- [Schwab StreetSmart positions](https://help.streetsmart.schwab.com/edge/1.4/Content/Positions.htm)
  documents position export and its fields.
- [Fidelity Portfolio Positions](https://www.fidelity.com/webcontent/ap002390-mlo-content/20.01/help/learn_open_positions.shtml)
  documents downloading the displayed positions as CSV.
- [Robinhood account documents](https://robinhood.com/us/en/support/articles/finding-your-account-documents/)
  documents custom account-activity reports.

Those sources establish export paths and semantics, not permanent schemas. The importer verifies
columns and keeps mismatches visible.
