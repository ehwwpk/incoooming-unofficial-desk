# Incoooming CSV import contract

## Usable slice

Incoooming's source gateway accepts up to eight UTF-8, UTF-16, or Windows-1252 CSV files per import
and 10 MB per file. Positions and activity exports may be uploaded together. Every import must pass a
preview before commit. The preview shows:

- detected broker profile, confidence, encoding, delimiter, and header row;
- positions and activity that will enter the book;
- ignored, needs-review, and rejected row counts;
- up to 20 row-numbered needs-review or rejection reasons per file, without echoing raw row values;
- the capabilities actually present in the selected files;
- warnings, including a selected-broker/file-shape mismatch.

Comma, tab, and semicolon delimiters are supported. Broker headers are matched by normalized field
meaning: column order, capitalization, punctuation, supported aliases, and unrelated extra columns
do not change a normalized record. An exact broker signature receives high confidence. A
structurally compatible alias-only table is treated as a medium-confidence generic shape rather
than being mislabeled as a specific broker. PDF, archive, HTML, binary, and unknown tabular content
fail closed.

Every stored book keeps file names, SHA-256 hashes, raw rows, source row numbers, row dispositions,
reasons, stable normalized fingerprints, and the accepted position, execution, cash-movement, and
lifecycle records. Exact duplicate files fail. Overlapping normalized records across different
selected files are compared as occurrences and ignored with a reason, so repeated real fills are
preserved without counting an overlapping export twice. Conflicting position snapshots for the same
account and symbol fail instead of being added together.

## Format adapters

The broker choice is operational, not a label. The importer currently recognizes:

- Schwab top-level web/StreetSmart position tables and recognized transaction columns, including
  preamble rows; lot-detail exports are not accepted as position snapshots;
- Fidelity recognized web-position headers and compatible activity columns, including compact
  option symbols;
- Robinhood custom account-activity CSV, not PDF statements;
- Webull executed quantities from order history; zero-filled rows are excluded;
- recognized IBKR multi-section Activity Statement CSV sections (`Trades`, `Open Positions`, and
  `Cash Transactions`), not arbitrary Flex schemas, XML, or PDF;
- Incoooming's generic position and activity templates.

Golden fixtures lock the intended semantics for each adapter. Generated variants reorder columns,
alter harmless header formatting, add unrelated fields, and change delimiter, encoding, and line
endings; they must produce the same normalized ledger records. Separate adversarial tests cover
malformed files, resource limits, duplicate headers, unsafe numbers, and non-CSV uploads. Broker
portals can still change exports, so preview remains mandatory. Webull order history supplies
executions, not positions or cash. A partially filled or later-cancelled order is retained when its
exported `Filled` quantity is nonzero; an unfilled row is ignored. IBKR Flex/custom statements vary;
only the recognized multi-section CSV layout is normalized.

## Truth rules

- Exported P/L is accepted only from an explicit P/L column.
- Numeric cells accept plain U.S. decimals, correctly grouped thousands, currency signs, and
  accounting parentheses. Non-finite values, scientific notation, percentages in money/quantity
  fields, malformed grouping, and decimal-comma values are rejected instead of reinterpreted.
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
- Position market-value direction follows signed quantity. A short position remains a liability even
  when an export prints its value as an unsigned magnitude; the raw source cell stays in the audit row.
- Buy executions are cash outflows and sell executions are cash inflows even when a broker prints
  its Amount column as an unsigned number. The raw amount remains preserved for audit.
- An adjusted/non-standard position without an explicit multiplier is held for review. An execution
  may still enter when the export supplies authoritative proceeds, but its multiplier remains
  unknown. Neither path silently forces the contract to 100x.
- Unknown nonzero cash is retained as unresolved evidence; unsafe option rows stay out of the
  ledger.
- Blank-symbol executions, zero-quantity executions, and lifecycle rows without a quantity do not
  enter the ledger as valid trades.
- Option position, execution, and lifecycle quantities must resolve to whole contract counts.
- Assignment and exercise rows retain exported delivered-share quantities and multipliers. When
  only delivered shares are present, a contract count is derived only when the shares divide
  exactly by a known multiplier. An adjusted contract with neither fact is held for review.
- Positions-only books cannot manufacture historical income. Activity-only books cannot establish
  current coverage.
- CSV capabilities are evidence-based. Balances, lots, Greeks, IV, price history, and live marks
  remain unavailable unless a separate provider supplies them.

CSV books are read-only. Importing a corrected export creates another book, preserving the prior
evidence rather than mutating it in place.

The app's CSV `IMPORTED` date is the local import time. Position tables generally do not carry a
reliable valuation timestamp, so Incoooming does not relabel import time as a broker-observed close.
Activity rows keep their own broker dates.

## Market-data boundary

CSV import builds the position/history ledger only. A later market-data provider may enrich a CSV
book with quotes, option chains, Greeks, IV, dividends, and bars, but that adapter must remain
separate. Missing or weak market data must never alter imported cash or executions.

## Official export references

- [Schwab StreetSmart positions](https://help.streetsmart.schwab.com/edge/1.32/Content/Positions.htm)
  documents position export and its fields.
- [Fidelity Portfolio Positions](https://www.fidelity.com/webcontent/ap002390-mlo-content/18.02/help/learn_open_positions.shtml)
  documents downloading the displayed positions as CSV.
- [Robinhood reports and statements](https://robinhood.com/us/en/support/articles/reports-and-statements/)
  documents custom account-activity reports.
- [Webull order-history export](https://www.webull.com/help/faq/992) documents that downloaded order
  history can include filled, partially filled, pending, cancelled, and failed orders.
- [IBKR Activity Flex Query reference](https://guides.interactivebrokers.com/reportingreference/reportguide/activity%20flex%20query%20reference.htm)
  documents its configurable report sections. Incoooming intentionally accepts only the recognized
  multi-section CSV layout described above.

Those sources establish export paths and semantics, not permanent schemas. The importer verifies
columns and keeps mismatches visible.
