from dataclasses import replace
from decimal import Decimal

from schwab_dashboard.application.dashboard.calculations import (
    OPTION_DAY_PERCENT_MARK_FLOOR,
    displayed_day_profit_loss_percent,
)
from schwab_dashboard.application.dashboard.models import PositionSummary
from schwab_dashboard.infrastructure.demo.dashboard import DemoDashboardReader
from schwab_dashboard.web.rendering import percent, templates

D = Decimal


def test_cheap_option_day_percent_is_withheld_and_floor_is_half_a_dollar() -> None:
    cheap = _row(
        asset_type="OPTION",
        mark=D("0.12"),
        day_profit_loss=D("-8.22"),
        day_profit_loss_percent=D("-2740.9"),
    )
    at_floor = replace(cheap, mark=OPTION_DAY_PERCENT_MARK_FLOOR)
    just_under = replace(cheap, mark=D("0.49"))
    missing_mark = replace(cheap, mark=None)

    assert displayed_day_profit_loss_percent(cheap) is None
    assert displayed_day_profit_loss_percent(just_under) is None
    assert displayed_day_profit_loss_percent(missing_mark) is None
    assert displayed_day_profit_loss_percent(at_floor) == D("-2740.9")
    assert cheap.day_profit_loss_percent == D("-2740.9")


def test_equities_and_funded_options_keep_broker_day_percent() -> None:
    stock = _row(asset_type="EQUITY", mark=D("54.53"), day_profit_loss_percent=D("-1.7"))
    penny_stock = _row(asset_type="EQUITY", mark=D("0.12"), day_profit_loss_percent=D("-50.0"))
    funded_option = _row(
        asset_type="option",
        mark=D("2.00"),
        day_profit_loss_percent=D("-12.0"),
    )
    funded_put = _row(
        asset_type="OPTION",
        symbol="URNM  260918P00050000",
        mark=D("1.70"),
        day_profit_loss_percent=D("9.8"),
        strategy="Short put",
    )

    assert displayed_day_profit_loss_percent(stock) == D("-1.7")
    assert displayed_day_profit_loss_percent(penny_stock) == D("-50.0")
    assert displayed_day_profit_loss_percent(funded_option) == D("-12.0")
    assert displayed_day_profit_loss_percent(funded_put) == D("9.8")


def test_positions_table_omits_exploded_option_percent_and_renames_heading() -> None:
    snapshot = DemoDashboardReader().execute()
    stock = next(item for item in snapshot.positions if item.asset_type == "EQUITY")
    cheap = _row(
        asset_type="OPTION",
        symbol="URNM  260918C00062000",
        description="URNM $62 call",
        mark=D("0.12"),
        market_value=D("-12"),
        day_profit_loss=D("-8.22"),
        day_profit_loss_percent=D("-2740.9"),
        strategy="Short call",
    )
    funded = _row(
        asset_type="OPTION",
        symbol="KTOS  260918C00075000",
        mark=D("2.00"),
        market_value=D("-200"),
        day_profit_loss=D("-24"),
        day_profit_loss_percent=D("-12.0"),
        strategy="Short call",
    )
    html = templates.env.get_template("partials/_positions.html").render(
        snapshot=replace(snapshot, positions=(stock, cheap, funded))
    )

    assert "<h2>Shares and options</h2>" in html
    assert "Shares and short calls" not in html
    assert "-2,740.9%" not in html
    assert "-2740.9%" not in html
    assert percent(stock.day_profit_loss_percent) in html
    assert "-12.0%" in html
    assert "-$8.22" in html
    assert "Option day-% is omitted under a $0.50 listed mark." in html
    assert percent(D("-2740.9")) == "-2,740.9%"


def _row(**overrides: object) -> PositionSummary:
    values: dict[str, object] = {
        "account_mask": "...1234",
        "symbol": "URNM  260918C00062000",
        "description": "URNM call",
        "asset_type": "OPTION",
        "quantity": D("-1"),
        "average_price": D("1.25"),
        "mark": D("0.12"),
        "market_value": D("-12"),
        "day_profit_loss": D("-8.22"),
        "day_profit_loss_percent": D("-2740.9"),
        "strategy": "Short call",
    }
    values.update(overrides)
    return PositionSummary(**values)  # type: ignore[arg-type]
