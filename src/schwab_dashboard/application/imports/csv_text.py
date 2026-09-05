from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from schwab_dashboard.application.imports.errors import CsvImportError

MAX_CSV_BYTES = 10 * 1024 * 1024
MAX_CSV_ROWS = 50_000
HEADER_SCAN_ROWS = 30

_PLAIN_DECIMAL = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)\Z")
_US_GROUPED_DECIMAL = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?\Z")
_MISSING_NUMBERS = frozenset({"--", "\N{EM DASH}", "N/A", "NA"})
_BINARY_SIGNATURES = (
    b"%PDF-",
    b"PK\x03\x04",
    b"PK\x05\x06",
    b"\x1f\x8b",
    b"\x89PNG\r\n\x1a\n",
    b"GIF8",
    b"\xff\xd8\xff",
)


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
    _reject_non_csv_content(content)
    text, encoding = _decode(content)
    delimiter = _delimiter(text)
    try:
        parsed = tuple(
            tuple(cell.strip() for cell in row)
            for row in csv.reader(io.StringIO(text), delimiter=delimiter, strict=True)
        )
    except csv.Error as exc:
        raise CsvImportError(f"The CSV structure is invalid: {exc}") from exc
    if len(parsed) > MAX_CSV_ROWS + HEADER_SCAN_ROWS + 1:
        raise CsvImportError(f"CSV files are limited to {MAX_CSV_ROWS:,} data rows.")
    if not any(any(cell for cell in row) for row in parsed):
        raise CsvImportError("The selected CSV file is empty.")
    return CsvText(rows=parsed, encoding=encoding, delimiter=delimiter)


def _reject_non_csv_content(content: bytes) -> None:
    sample = content[:4096].lstrip()
    if sample.startswith(b"\xef\xbb\xbf"):
        sample = sample[3:].lstrip()
    lowered = sample.lower()
    if sample.startswith(_BINARY_SIGNATURES) or lowered.startswith(
        (b"<!doctype html", b"<html", b"<?xml", b"{\\rtf")
    ):
        raise CsvImportError("The selected file is not CSV text.")
    if not content.startswith((b"\xff\xfe", b"\xfe\xff")) and b"\x00" in sample:
        raise CsvImportError("The selected file appears to be binary, not CSV text.")


def header_key(value: str) -> str:
    key = "".join(character for character in value.lower() if character.isalnum())
    # A currency and a percentage column are not punctuation variants of the
    # same field. Preserve their unit so exports containing both cannot
    # collapse into one ambiguous key.
    if "%" in value and not key.endswith("percent"):
        return f"{key}percent"
    if "$" in value and not key.endswith("dollar"):
        return f"{key}dollar"
    return key


def row_dict(headers: tuple[str, ...], values: tuple[str, ...]) -> dict[str, str]:
    padded = values + ("",) * max(0, len(headers) - len(values))
    result = {header: padded[index] for index, header in enumerate(headers)}
    if len(values) > len(headers):
        result["_extra"] = " | ".join(values[len(headers) :])
    return result


def validate_headers(headers: tuple[str, ...]) -> None:
    """Reject headers whose punctuation/casing would collapse two columns into one."""

    seen: dict[str, str] = {}
    duplicates: set[str] = set()
    for header in headers:
        key = header_key(header)
        if not key:
            continue
        if key in seen:
            duplicates.add(key)
        else:
            seen[key] = header
    if duplicates:
        names = ", ".join(sorted(duplicates))
        raise CsvImportError(f"The CSV header has duplicate or ambiguous columns: {names}.")


def decimal_cell(value: str, *, required: bool = False, label: str = "number") -> Decimal | None:
    """Parse an unambiguous U.S.-formatted broker number or fail closed."""

    cleaned = value.strip().replace("\u00a0", " ")
    if not cleaned or cleaned.upper() in _MISSING_NUMBERS:
        if required:
            raise CsvImportError(f"{label} is blank")
        return None
    if "%" in cleaned or any(character.isspace() for character in cleaned):
        raise CsvImportError(f"{label} {value!r} is not a valid broker number")

    parenthesized = cleaned.startswith("(") and cleaned.endswith(")")
    if parenthesized:
        cleaned = cleaned[1:-1]
    elif "(" in cleaned or ")" in cleaned:
        raise CsvImportError(f"{label} {value!r} is not a valid broker number")

    sign = ""
    if cleaned[:1] in {"+", "-"}:
        sign, cleaned = cleaned[0], cleaned[1:]
    if cleaned.startswith("$"):
        cleaned = cleaned[1:]
    if not sign and cleaned[:1] in {"+", "-"}:
        sign, cleaned = cleaned[0], cleaned[1:]
    if parenthesized and sign:
        raise CsvImportError(f"{label} {value!r} has two sign conventions")

    if "," in cleaned:
        if _US_GROUPED_DECIMAL.fullmatch(cleaned) is None:
            raise CsvImportError(
                f"{label} {value!r} has an ambiguous or invalid thousands separator"
            )
        cleaned = cleaned.replace(",", "")
    elif _PLAIN_DECIMAL.fullmatch(cleaned) is None:
        raise CsvImportError(f"{label} {value!r} is not a valid broker number")

    try:
        result = Decimal(f"{sign}{cleaned}")
    except InvalidOperation as exc:
        raise CsvImportError(f"{label} {value!r} is not a valid broker number") from exc
    if not result.is_finite():
        raise CsvImportError(f"{label} {value!r} is not finite")
    return -result if parenthesized else result


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
