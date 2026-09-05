from collections.abc import Sequence
from dataclasses import replace
from decimal import Decimal

from schwab_dashboard.application.dashboard.models import AllocationSlice, PositionSummary
from schwab_dashboard.infrastructure.demo.fixtures.short_puts import PUT_FIXTURES
from schwab_dashboard.infrastructure.schwab.option_symbol import parse_occ_option_symbol

D = Decimal


def build_positions() -> tuple[PositionSummary, ...]:
    rows = (
        (
            "CVX",
            "Chevron shares",
            "EQUITY",
            "700",
            "155.40",
            "186.56",
            "130592",
            "-1869",
            "-1.41",
            "Covered calls",
        ),
        (
            "KTOS",
            "Kratos Defense shares",
            "EQUITY",
            "800",
            "31.75",
            "60.77",
            "48616",
            "2688",
            "5.85",
            "Covered calls",
        ),
        (
            "URNM",
            "Sprott Uranium Miners ETF",
            "EQUITY",
            "500",
            "44.20",
            "54.53",
            "27265",
            "735",
            "2.77",
            "Covered calls",
        ),
        (
            "CVX 260814C00195000",
            "Aug 14 195 call",
            "OPTION",
            "-1",
            "2.10",
            "2.50",
            "-250",
            "-24",
            "-8.76",
            "Covered call",
        ),
        (
            "CVX 260821C00205000",
            "Aug 21 205 call",
            "OPTION",
            "-1",
            "1.80",
            "1.10",
            "-110",
            "12",
            "9.84",
            "Covered call",
        ),
        (
            "CVX 260918C00215000",
            "Sep 18 215 call",
            "OPTION",
            "-4",
            "2.025",
            "1.20",
            "-480",
            "52",
            "9.77",
            "Covered call",
        ),
        (
            "KTOS 260828C00075000",
            "Aug 28 75 call",
            "OPTION",
            "-5",
            "2.45",
            "0.70",
            "-350",
            "62",
            "15.05",
            "Covered call",
        ),
        (
            "KTOS 260925C00090000",
            "Sep 25 90 call",
            "OPTION",
            "-3",
            "1.55",
            "0.60",
            "-180",
            "18",
            "9.09",
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
    puts = tuple(
        PositionSummary(
            account_mask="...4831",
            symbol=item.option_symbol,
            description=f"{item.expires_on:%b %d} {item.strike:g} put",
            asset_type="OPTION",
            quantity=-D(item.contracts),
            average_price=item.entry_credit_per_share,
            mark=item.mark_per_share,
            market_value=-item.mark_per_share * item.contracts * 100,
            day_profit_loss=item.day_profit_loss,
            day_profit_loss_percent=(
                item.day_profit_loss
                / (item.mark_per_share * item.contracts * 100 + item.day_profit_loss)
                * 100
            ).quantize(D("0.01")),
            strategy="Cash-secured put",
            underlying_symbol=item.symbol,
            option_type="PUT",
            expiration_date=item.expires_on,
            strike=item.strike,
            open_profit_loss=(item.entry_credit - item.mark_per_share * item.contracts * 100),
            contract_multiplier=D("100"),
            multiplier_source="fictional_standard",
            is_non_standard=False,
        )
        for item in PUT_FIXTURES
    )
    return (*(_position(row) for row in rows), *puts)


def build_allocations(
    positions: Sequence[PositionSummary], cash_value: Decimal
) -> tuple[AllocationSlice, ...]:
    equities = {
        item.symbol: item.market_value or D("0")
        for item in positions
        if item.asset_type == "EQUITY"
    }
    option_value = abs(
        sum(
            ((item.market_value or D("0")) for item in positions if item.asset_type == "OPTION"),
            D("0"),
        )
    )
    rows = (
        ("CVX shares", equities["CVX"], "amber"),
        ("KTOS shares", equities["KTOS"], "emerald"),
        ("URNM shares", equities["URNM"], "olive"),
        ("Cash", cash_value, "green"),
        ("Short options", option_value, "red"),
    )
    total = sum((value for _, value, _ in rows), D("0"))
    allocations = tuple(
        AllocationSlice(label, value, (value / total * 100).quantize(D("0.01")), tone)
        for label, value, tone in rows
    )
    remainder = D("100") - sum((item.percent for item in allocations), D("0"))
    return (replace(allocations[0], percent=allocations[0].percent + remainder), *allocations[1:])


def _position(row: tuple[str, ...]) -> PositionSummary:
    option = parse_occ_option_symbol(row[0]) if row[2] == "OPTION" else None
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
        open_profit_loss=(D(row[5]) - D(row[4])) * D(row[3]) * (100 if option else 1),
        underlying_symbol=option.underlying_symbol if option else None,
        option_type=option.option_type if option else None,
        expiration_date=option.expiration_date if option else None,
        strike=option.strike if option else None,
        contract_multiplier=D("100") if option else None,
        multiplier_source="fictional_standard" if option else None,
        is_non_standard=False if option else None,
    )
