from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

from schwab_dashboard.application.imports.csv_profiles import select_profile
from schwab_dashboard.application.imports.csv_text import read_csv_text, row_dict
from schwab_dashboard.application.imports.errors import CsvImportError
from schwab_dashboard.application.imports.ibkr_parser import is_ibkr_statement, parse_ibkr_statement
from schwab_dashboard.application.imports.row_normalizer import (
    detect_file_kind,
    field_map,
    is_summary_row,
    normalize_activity_row,
    normalize_position_row,
)
from schwab_dashboard.domain.data_source import (
    BrokerKind,
    ImportRecordKind,
    ImportRowDisposition,
    ParsedCsvFile,
    ParsedImportRecord,
    ParsedImportRow,
)


def parse_csv_file(
    *, filename: str, content: bytes, broker: BrokerKind = BrokerKind.GENERIC
) -> ParsedCsvFile:
    table = read_csv_text(content)
    digest = hashlib.sha256(content).hexdigest()
    if is_ibkr_statement(table):
        return parse_ibkr_statement(
            filename=filename,
            table=table,
            digest=digest,
            requested_broker=broker,
        )
    try:
        match = select_profile(table, broker)
    except ValueError as exc:
        raise CsvImportError(str(exc)) from exc
    headers = tuple(table.rows[match.header_row - 1])
    mapped_fields = field_map(headers)
    file_kind = detect_file_kind(mapped_fields)
    records: list[ParsedImportRecord] = []
    outcomes: list[ParsedImportRow] = []
    warnings: list[str] = []
    if match.profile.broker is not broker and broker is not BrokerKind.GENERIC:
        warnings.append(
            f"Selected {broker.value.title()}, but the columns match "
            f"{match.profile.broker.value.title()} ({match.profile.name})."
        )
    if table.encoding != "utf-8":
        warnings.append(f"Decoded {table.encoding} broker text safely.")
    for index, values in enumerate(table.rows[: match.header_row - 1], start=1):
        if any(values):
            outcomes.append(
                ParsedImportRow(
                    source_row_number=index,
                    disposition=ImportRowDisposition.IGNORED,
                    raw={"_line": " | ".join(values)},
                    reason="Broker preamble before the detected header.",
                )
            )
    for index, values in enumerate(table.rows[match.header_row :], start=match.header_row + 1):
        raw = row_dict(headers, values)
        if not any(raw.values()):
            continue
        if is_summary_row(raw):
            outcomes.append(
                _outcome(index, raw, ImportRowDisposition.IGNORED, "Summary or footer row.")
            )
            continue
        try:
            result = (
                normalize_position_row(raw, mapped_fields=mapped_fields)
                if file_kind == "positions"
                else normalize_activity_row(
                    raw, mapped_fields=mapped_fields, broker=match.profile.broker
                )
            )
            if result is None:
                outcomes.append(
                    _outcome(index, raw, ImportRowDisposition.IGNORED, "Blank or non-ledger row.")
                )
                continue
            kind, payload = result
            if payload.pop("_needs_review", False):
                reason = str(payload.pop("_review_reason", "The row needs review."))
                outcomes.append(_outcome(index, raw, ImportRowDisposition.NEEDS_REVIEW, reason))
                continue
            fingerprint = _fingerprint(kind, payload)
            record = ParsedImportRecord(
                kind=kind,
                external_key=f"csv:{fingerprint}",
                fingerprint=fingerprint,
                source_row_number=index,
                normalized=payload,
                raw=raw,
            )
            records.append(record)
            outcomes.append(
                ParsedImportRow(
                    source_row_number=index,
                    disposition=ImportRowDisposition.IMPORTED,
                    raw=raw,
                    record=record,
                )
            )
        except CsvImportError as exc:
            outcomes.append(_outcome(index, raw, ImportRowDisposition.REJECTED, str(exc)))
    records, outcomes = _disambiguate(records, outcomes)
    rejected = sum(row.disposition is ImportRowDisposition.REJECTED for row in outcomes)
    review = sum(row.disposition is ImportRowDisposition.NEEDS_REVIEW for row in outcomes)
    if rejected:
        warnings.append(f"{rejected} row(s) were rejected; none entered the ledger.")
    if review:
        warnings.append(f"{review} row(s) need review; none entered the ledger.")
    if not records:
        raise CsvImportError(
            "No safe position or activity rows were found. Preview did not import anything."
        )
    return ParsedCsvFile(
        filename=Path(filename).name or "import.csv",
        file_kind=file_kind,
        headers=headers,
        records=tuple(records),
        rows=tuple(outcomes),
        warnings=tuple(warnings),
        sha256=digest,
        detected_broker=match.profile.broker,
        profile=match.profile.name,
        confidence=match.confidence,
        header_row=match.header_row,
        encoding=table.encoding,
        delimiter=table.delimiter,
        capabilities=_capabilities(file_kind, records),
    )


def _fingerprint(kind: ImportRecordKind, payload: dict[str, object]) -> str:
    canonical = {
        key: value
        for key, value in payload.items()
        if key not in {"external_key", "order_external_key"}
    }
    body = json.dumps(
        {"kind": kind.value, "record": canonical}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:32]


def _capabilities(file_kind: str, records: list[ParsedImportRecord]) -> tuple[str, ...]:
    if file_kind == "positions":
        return ("positions",)
    present = {record.kind for record in records}
    capabilities: set[str] = set()
    if ImportRecordKind.EXECUTION in present:
        capabilities.add("executions")
    if ImportRecordKind.CASH_MOVEMENT in present:
        capabilities.add("cash_movements")
        if any(
            record.normalized.get("movement_type") == "dividend"
            for record in records
            if record.kind is ImportRecordKind.CASH_MOVEMENT
        ):
            capabilities.add("dividends")
    if ImportRecordKind.LIFECYCLE in present:
        capabilities.add("option_lifecycle")
    return tuple(sorted(capabilities))


def _disambiguate(
    records: list[ParsedImportRecord], outcomes: list[ParsedImportRow]
) -> tuple[list[ParsedImportRecord], list[ParsedImportRow]]:
    totals = Counter(record.fingerprint for record in records)
    seen: Counter[str] = Counter()
    replacements: dict[int, ParsedImportRecord] = {}
    result: list[ParsedImportRecord] = []
    for record in records:
        seen[record.fingerprint] += 1
        suffix = f":{seen[record.fingerprint]}" if totals[record.fingerprint] > 1 else ""
        updated = replace(record, external_key=f"csv:{record.fingerprint}{suffix}")
        replacements[record.source_row_number] = updated
        result.append(updated)
    updated_rows = [
        replace(row, record=replacements[row.source_row_number]) if row.record is not None else row
        for row in outcomes
    ]
    return result, updated_rows


def _outcome(
    row_number: int, raw: dict[str, str], disposition: ImportRowDisposition, reason: str
) -> ParsedImportRow:
    return ParsedImportRow(row_number, disposition, raw, reason)
