from decimal import Decimal

from schwab_dashboard.application.dashboard.models import AllocationSlice, PositionSummary

D = Decimal


def build_positions() -> tuple[PositionSummary, ...]:
    rows = (
        (
            "CVX",
            "Chevron shares",
            "EQUITY",
            "700",
            "155.40",
            "192.26",
            "134582",
            "-840",
            "-0.62",
            "Covered calls",
        ),
        (
            "KTOS",
            "Kratos Defense shares",
            "EQUITY",
            "800",
            "31.75",
            "65.19",
            "52152",
            "1760",
            "3.49",
            "Covered calls",
        ),
        (
            "URNM",
            "Sprott Uranium Miners ETF",
            "EQUITY",
            "500",
            "44.20",
            "54.57",
            "27285",
            "755",
            "2.85",
            "Covered calls",
        ),
        (
            "CVX 260904C00235000",
            "Sep 04 235 call",
            "OPTION",
            "-4",
            "2.10",
            "1.20",
            "-480",
            "95",
            "16.52",
            "Covered call",
        ),
        (
            "CVX 260918C00225000",
            "Sep 18 225 call",
            "OPTION",
            "-2",
            "1.80",
            "1.80",
            "-360",
            "44",
            "10.89",
            "Covered call",
        ),
        (
            "KTOS 260918C00075000",
            "Sep 18 75 call",
            "OPTION",
            "-5",
            "2.45",
            "2.45",
            "-1225",
            "-230",
            "-23.12",
            "Covered call",
        ),
        (
            "KTOS 260918C00082500",
            "Sep 18 82.5 call",
            "OPTION",
            "-3",
            "1.55",
            "1.10",
            "-330",
            "35",
            "9.59",
            "Covered call",
        ),
        (
            "URNM 260918C00067500",
            "Sep 18 67.5 call",
            "OPTION",
            "-4",
            "1.25",
            "0.92",
            "-368",
            "68",
            "15.60",
            "Covered call",
        ),
    )
    return tuple(_position(row) for row in rows)


def build_allocations() -> tuple[AllocationSlice, ...]:
    return (
        AllocationSlice("CVX shares", D("134582"), D("57.14"), "amber"),
        AllocationSlice("KTOS shares", D("52152"), D("22.14"), "cyan"),
        AllocationSlice("URNM shares", D("27285"), D("11.59"), "violet"),
        AllocationSlice("Cash", D("18750"), D("7.96"), "green"),
        AllocationSlice("Short calls", D("2763"), D("1.17"), "red"),
    )


def _position(row: tuple[str, ...]) -> PositionSummary:
    return PositionSummary(
        account_mask="...4831",
        symbol=row[0],
        description=row[1],
        asset_type=row[2],
        quantity=D(row[3]),
        average_price=D(row[4]),
        mark=D(row[5]),
        market_value=D(row[6]),
        day_profit_loss=D(row[7]),
        day_profit_loss_percent=D(row[8]),
        strategy=row[9],
    )
