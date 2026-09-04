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
- A broker date without a time-zone offset keeps the displayed U.S. market date. It is not treated
  as midnight UTC and shifted to the prior session.
- Explicit deposits and withdrawals are external cash flow, never option or dividend income.
  Direction words normalize unsigned deposits to inflows and unsigned withdrawals to outflows.
- A bare journal or transfer label is ambiguous. It is retained as `other` cash and blocks the
  affected return link instead of being guessed as owner funding or investment performance.
- Dividends, interest, fees, withholding, and transfers remain separate movement types. Unsigned
  fees and withholding are normalized to cash outflows.
- Standard options may use an explicit exported multiplier or a visible `assumed_standard` 100x
  multiplier.
- When a standard option export omits total market value or per-share mark, the importer derives the
  missing side using quantity and the contract multiplier. The same rule applies when deriving a
  per-share average from total cost basis.
- Buy executions are cash outflows and sell executions are cash inflows even when a broker prints
  its Amount column as an unsigned number. The raw amount remains preserved for audit.
- An adjusted/non-standard position without an explicit multiplier is held for review. An execution
  may still enter when the export supplies authoritative proceeds, but its multiplier remains
  unknown. Neither path silently forces the contract to 100x.
- Unknown nonzero cash is retained as unresolved evidence; unsafe option rows stay out of the
  ledger.
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
- [IBKR Trades](https://www.ibkrguides.com/reportingreference/reportguide/transactions_costs_charges.htm)
  defines signed proceeds separately from commissions and documents its Activity Statement trade
  fields.

Those sources establish export paths and semantics, not permanent schemas. The importer verifies
columns and keeps mismatches visible.
