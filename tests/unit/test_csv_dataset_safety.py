from __future__ import annotations

from typing import cast
from unittest.mock import Mock

import pytest

from schwab_dashboard.application.ports.source_store import SourceDatasetStore
from schwab_dashboard.application.services.import_csv_dataset import ImportCsvDataset
from schwab_dashboard.domain.data_source import BrokerKind


def _service() -> ImportCsvDataset:
    return ImportCsvDataset(store=cast(SourceDatasetStore, Mock()))


def _activity(*rows: bytes) -> bytes:
    return (
        b"Account,Date,Action,Symbol,Description,Quantity,Price,Fees,Amount\n"
        + b"\n".join(rows)
        + b"\n"
    )


def _positions(*rows: bytes, extra_header: bytes = b"") -> bytes:
    suffix = b"," + extra_header if extra_header else b""
    return (
        b"Account,Symbol,Quantity,Last Price,Market Value"
        + suffix
        + b"\n"
        + b"\n".join(rows)
        + b"\n"
    )


def test_overlap_deduplication_uses_multiset_occurrences_not_file_local_keys() -> None:
    repeated = b"Brokerage 4321,08/01/2026,Sell,CVX,CVX sale,1,195,0,195"
    first = _activity(repeated, repeated)
    second = _activity(repeated)

    preview = _service().preview(
        name="Overlapping history",
        broker=BrokerKind.GENERIC,
        files=(("long.csv", first), ("short.csv", second)),
    )

    assert preview.activity_count == 2
    assert preview.files[1].ignored_count == 1
    assert len({record.external_key for file in preview.files for record in file.records}) == 2


def test_identical_position_snapshot_overlap_is_removed() -> None:
    row = b"Brokerage 4321,CVX,100,195,19500"
    first = _positions(row)
    second = _positions(row + b",same snapshot", extra_header=b"Note")

    preview = _service().preview(
        name="Same snapshot",
        broker=BrokerKind.GENERIC,
        files=(("one.csv", first), ("two.csv", second)),
    )

    assert preview.position_count == 1
    assert preview.files[1].ignored_count == 1


def test_conflicting_position_snapshots_fail_instead_of_stacking_holdings() -> None:
    first = _positions(b"Brokerage 4321,CVX,100,195,19500")
    second = _positions(b"Brokerage 4321,CVX,125,196,24500")

    with pytest.raises(ValueError, match="Conflicting position snapshots"):
        _service().preview(
            name="Conflicting snapshots",
            broker=BrokerKind.GENERIC,
            files=(("older.csv", first), ("newer.csv", second)),
        )


def test_lot_detail_or_duplicate_position_rows_fail_instead_of_double_counting() -> None:
    rows = (
        b"Brokerage 4321,CVX,50,195,9750",
        b"Brokerage 4321,CVX,50,195,9750",
    )

    with pytest.raises(ValueError, match="aggregated position snapshot"):
        _service().preview(
            name="Lot detail",
            broker=BrokerKind.GENERIC,
            files=(("lots.csv", _positions(*rows)),),
        )


def test_mixed_detected_brokers_require_separate_books() -> None:
    schwab = b"Symbol,Quantity,Current Price,Market Value\nCVX,100,195,19500\n"
    webull = (
        b"Filled Time,Symbol,Side,Filled,Total Qty,Avg Price,Status\n"
        b"08/01/2026 10:31:00,CVX,SELL,100,100,195,Filled\n"
    )

    with pytest.raises(ValueError, match="more than one broker"):
        _service().preview(
            name="Mixed brokers",
            broker=BrokerKind.GENERIC,
            files=(("schwab.csv", schwab), ("webull.csv", webull)),
        )


def test_exact_detected_broker_is_stored_instead_of_generic_label() -> None:
    store = Mock()
    service = ImportCsvDataset(store=cast(SourceDatasetStore, store))
    schwab = b"Symbol,Quantity,Current Price,Market Value\nCVX,100,195,19500\n"

    service.execute(
        name="Detected Schwab",
        broker=BrokerKind.GENERIC,
        files=(("positions.csv", schwab),),
    )

    assert store.create_dataset.call_args.kwargs["broker"] is BrokerKind.SCHWAB
