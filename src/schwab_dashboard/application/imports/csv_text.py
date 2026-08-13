from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from schwab_dashboard.application.imports.errors import CsvImportError

MAX_CSV_BYTES = 10 * 1024 * 1024
MAX_CSV_ROWS = 50_000
HEADER_SCAN_ROWS = 30


@dataclass(frozen=True, slots=True)
class CsvText:
    rows: tuple[tuple[str, ...], ...]
    encoding: str
    delimiter: str


def read_csv_text(content: bytes) -> CsvText:
    if not content:
        raise CsvImportError("The selected CSV file is empty.")
    if len(content) > MAX_CSV_BYTES:
        raise CsvImportError("CSV files are limited to 10 MB each.")
    text, encoding = _decode(content)
    delimiter = _delimiter(text)
    try:
        parsed = tuple(
            tuple(cell.strip() for cell in row)
            for row in csv.reader(io.StringIO(text), delimiter=delimiter)
        )
    except csv.Error as exc:
        raise CsvImportError(f"The CSV structure is invalid: {exc}") from exc
    if len(parsed) > MAX_CSV_ROWS + HEADER_SCAN_ROWS + 1:
        raise CsvImportError(f"CSV files are limited to {MAX_CSV_ROWS:,} data rows.")
    if not any(any(cell for cell in row) for row in parsed):
        raise CsvImportError("The selected CSV file is empty.")
    return CsvText(rows=parsed, encoding=encoding, delimiter=delimiter)


def header_key(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def row_dict(headers: tuple[str, ...], values: tuple[str, ...]) -> dict[str, str]:
    padded = values + ("",) * max(0, len(headers) - len(values))
    result = {header: padded[index] for index, header in enumerate(headers)}
    if len(values) > len(headers):
        result["_extra"] = " | ".join(values[len(headers) :])
    return result


def _decode(content: bytes) -> tuple[str, str]:
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return content.decode("utf-16"), "utf-16"
        except UnicodeDecodeError as exc:
            raise CsvImportError("The UTF-16 broker export is damaged.") from exc
    try:
        return content.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        try:
            return content.decode("cp1252"), "windows-1252"
        except UnicodeDecodeError as exc:
            raise CsvImportError(
                "The file is not valid UTF-8, UTF-16, or Windows-1252 text."
            ) from exc


def _delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:20])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;").delimiter
    except csv.Error:
        counts = {candidate: sample.count(candidate) for candidate in (",", "\t", ";")}
        return max(counts, key=lambda candidate: counts[candidate]) if max(counts.values()) else ","
