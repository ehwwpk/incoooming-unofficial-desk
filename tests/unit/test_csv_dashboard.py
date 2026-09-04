from datetime import UTC, datetime

from schwab_dashboard.domain.data_source import BrokerKind, DatasetState, SourceDataset
from schwab_dashboard.infrastructure.imports.csv_dashboard import CsvDashboardReader


class _Store:
    def __init__(self, dataset: SourceDataset, records: tuple[dict[str, object], ...]) -> None:
        self.dataset = dataset
        self.records = records

    def get_dataset(self, dataset_id: str) -> SourceDataset | None:
        return self.dataset if dataset_id == self.dataset.id else None

    def load_records(self, dataset_id: str) -> tuple[dict[str, object], ...]:
        return self.records if dataset_id == self.dataset.id else ()


def test_csv_dashboard_uses_the_market_date_at_the_utc_day_boundary() -> None:
    created_at = datetime(2026, 8, 11, 1, tzinfo=UTC)  # Aug 10 in New York.
    dataset = SourceDataset(
        id="dataset",
        name="Boundary import",
        broker=BrokerKind.GENERIC,
        state=DatasetState.READY,
        created_at=created_at,
        file_count=1,
        position_count=1,
        activity_count=0,
        ignored_count=0,
        review_count=0,
        rejected_count=0,
        capabilities=("positions",),
        warnings=(),
    )
    records = (
        {
            "kind": "position",
            "normalized": {
                "account_id": "account-a",
                "account_mask": "...1234",
                "symbol": "XYZ  260811C00100000",
                "description": "XYZ Aug 11 100 Call",
                "asset_type": "OPTION",
                "quantity": "-1",
                "average_price": "1",
                "mark": "0.5",
                "market_value": "-50",
                "day_profit_loss": "0",
                "day_profit_loss_percent": "0",
                "underlying_symbol": "XYZ",
                "option_type": "CALL",
                "expiration_date": "2026-08-11",
                "strike": "100",
                "open_profit_loss": "50",
                "contract_multiplier": "100",
                "multiplier_source": "broker",
                "is_non_standard": "False",
            },
        },
    )

    snapshot = CsvDashboardReader(
        store=_Store(dataset, records),  # type: ignore[arg-type]
        dataset_id=dataset.id,
        clock=lambda: created_at,
    ).execute()

    assert snapshot.live_position_book is not None
    assert snapshot.live_position_book.calls[0].days_to_expiration == 1
