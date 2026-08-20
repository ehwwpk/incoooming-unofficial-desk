from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.dashboard.live_call_history import project_call_sale_records
from schwab_dashboard.infrastructure.demo.dashboard import DemoDashboardReader
from schwab_dashboard.web.rendering import templates

D = Decimal
AS_OF = date(2026, 8, 18)


def test_same_order_roll_is_two_tickets_with_shared_campaign() -> None:
    rows = (
        _execution(
            "open-one", "order-1", "KTOS  260814C00065000", "sell", "opening", "200", 1, strike="65"
        ),
        _execution(
            "close-one", "roll-1", "KTOS  260814C00065000", "buy", "closing", "-50", 2, strike="65"
        ),
        _execution(
            "open-two",
            "roll-1",
            "KTOS  260918C00070000",
            "sell",
            "opening",
            "125",
            2,
            strike="70",
            expires=date(2026, 9, 18),
        ),
        _execution(
            "close-two",
            "close-2",
            "KTOS  260918C00070000",
            "buy",
            "closing",
            "-25",
            3,
            strike="70",
            expires=date(2026, 9, 18),
        ),
    )

    tickets = _project(rows)
    assert [item.record_id for item in tickets] == ["open-one", "open-two"]
    first, second = tickets
    assert first.outcome == "Rolled"
    assert second.outcome == "Closed"
    assert first.parent_record_id is None
    assert second.parent_record_id == "open-one"
    assert first.campaign_id == second.campaign_id == "open-one"
    assert first.buyback_cost == D("50")
    assert first.net_cash == D("150")
    assert second.buyback_cost == D("25")
    assert second.net_cash == D("100")
    assert first.contracts == 1
    assert second.contracts == 1
    assert first.option_side == "CALL"
    assert first.sale_signal == ""
    assert first.policy_id == ""
    assert first.closed_on == date(2026, 8, 2)
    assert second.closed_on == date(2026, 8, 3)


def test_split_orders_are_separate_tickets_without_a_parent() -> None:
    rows = (
        _execution(
            "open-one", "order-a", "KTOS  260814C00065000", "sell", "opening", "200", 1, strike="65"
        ),
        _execution(
            "close-one", "order-b", "KTOS  260814C00065000", "buy", "closing", "-50", 2, strike="65"
        ),
        _execution(
            "open-two",
            "order-c",
            "KTOS  260918C00070000",
            "sell",
            "opening",
            "125",
            3,
            strike="70",
            expires=date(2026, 9, 18),
        ),
    )

    tickets = _project(rows)
    assert [item.outcome for item in tickets] == ["Closed", "Open"]
    assert all(item.parent_record_id is None for item in tickets)
    assert tickets[0].campaign_id != tickets[1].campaign_id
    assert tickets[1].closed_on is None
    assert tickets[1].buyback_cost == D("0")


def test_put_opening_is_a_put_ticket() -> None:
    tickets = _project(
        (
            _execution(
                "put-open",
                "put-1",
                "URNM  260918P00050000",
                "sell",
                "opening",
                "120",
                1,
                strike="50",
                expires=date(2026, 9, 18),
                option_side="put",
                underlying="URNM",
            ),
        ),
        daily_bars=({"symbol": "URNM", "trade_date": date(2026, 8, 1), "close": D("55")},),
    )
    assert len(tickets) == 1
    ticket = tickets[0]
    assert ticket.option_side == "PUT"
    assert ticket.outcome == "Open"
    assert ticket.symbol == "URNM"
    assert ticket.underlying_at_sale == D("55")
    assert ticket.strike_upside_percent == D("9.09")


def test_long_option_lifecycle_is_not_a_ticket() -> None:
    rows = (
        _execution(
            "long-open",
            "order",
            "KTOS  260918C00065000",
            "buy",
            "opening",
            "-100",
            1,
            strike="65",
        ),
    )
    lifecycle = (
        {
            "external_key": "long-expiry",
            "occurred_at": date(2026, 8, 2),
            "event_type": "expiration",
            "option_quantity": D("1"),
            "symbol": "KTOS  260918C00065000",
            "underlying_symbol": "KTOS",
            "option_side": "call",
            "strike": D("65"),
            "expiration_date": date(2026, 9, 18),
        },
    )
    assert _project(rows, lifecycle=lifecycle) == ()


def test_short_expiration_is_expired_not_left_open() -> None:
    rows = (
        _execution(
            "open-one", "order-1", "KTOS  260814C00065000", "sell", "opening", "200", 1, strike="65"
        ),
    )
    lifecycle = (
        {
            "external_key": "short-expiry",
            "occurred_at": date(2026, 8, 14),
            "event_type": "expiration",
            "option_quantity": D("1"),
            "symbol": "KTOS  260814C00065000",
            "underlying_symbol": "KTOS",
            "option_side": "call",
            "strike": D("65"),
            "expiration_date": date(2026, 8, 14),
        },
    )
    tickets = _project(rows, lifecycle=lifecycle)
    assert len(tickets) == 1
    assert tickets[0].outcome == "Expired"
    assert tickets[0].closed_on == date(2026, 8, 14)
    assert tickets[0].buyback_cost == D("0")
    assert tickets[0].net_cash == D("200")


def test_short_assignment_is_assigned() -> None:
    rows = (
        _execution(
            "open-one", "order-1", "KTOS  260814C00065000", "sell", "opening", "200", 1, strike="65"
        ),
    )
    lifecycle = (
        {
            "external_key": "assigned",
            "occurred_at": date(2026, 8, 12),
            "event_type": "assignment",
            "option_quantity": D("1"),
            "symbol": "KTOS  260814C00065000",
            "underlying_symbol": "KTOS",
            "option_side": "call",
            "strike": D("65"),
            "expiration_date": date(2026, 8, 14),
        },
    )
    assert _project(rows, lifecycle=lifecycle)[0].outcome == "Assigned"


def test_partial_buyback_keeps_original_sale_size() -> None:
    rows = (
        _execution(
            "open-five",
            "open-1",
            "KTOS  260918C00065000",
            "sell",
            "opening",
            "500",
            1,
            quantity=5,
            strike="65",
            expires=date(2026, 9, 18),
        ),
        _execution(
            "close-two",
            "close-1",
            "KTOS  260918C00065000",
            "buy",
            "closing",
            "-80",
            4,
            quantity=2,
            strike="65",
            expires=date(2026, 9, 18),
        ),
    )
    tickets = _project(rows)
    assert len(tickets) == 1
    ticket = tickets[0]
    assert ticket.outcome == "Open"
    assert ticket.contracts == 5
    assert ticket.buyback_cost == D("80")
    assert ticket.net_cash == D("420")
    assert ticket.closed_on is None
    assert ticket.parent_record_id is None


def test_one_close_splits_cash_across_two_openings() -> None:
    rows = (
        _execution(
            "open-a", "oa", "KTOS  260814C00065000", "sell", "opening", "200", 1, strike="65"
        ),
        _execution(
            "open-b", "ob", "KTOS  260814C00065000", "sell", "opening", "220", 2, strike="65"
        ),
        _execution(
            "close",
            "oc",
            "KTOS  260814C00065000",
            "buy",
            "closing",
            "-90",
            3,
            quantity=2,
            strike="65",
        ),
    )
    first, second = _project(rows)
    assert [item.outcome for item in (first, second)] == ["Closed", "Closed"]
    assert first.buyback_cost == D("45")
    assert second.buyback_cost == D("45")
    assert first.net_cash == D("155")
    assert second.net_cash == D("175")


def test_missing_spot_does_not_invent_a_gap() -> None:
    tickets = _project(
        (
            _execution(
                "open-one",
                "order-1",
                "KTOS  260814C00065000",
                "sell",
                "opening",
                "200",
                1,
                strike="65",
            ),
        )
    )
    assert tickets[0].underlying_at_sale == D("0")
    assert tickets[0].strike_upside_percent == D("0")


def test_call_gap_follows_sign_when_spot_exists() -> None:
    otm = _project(
        (
            _execution(
                "otm", "order-1", "KTOS  260814C00065000", "sell", "opening", "200", 1, strike="65"
            ),
        ),
        daily_bars=({"symbol": "KTOS", "trade_date": date(2026, 8, 1), "close": D("60")},),
    )[0]
    itm = _project(
        (
            _execution(
                "itm", "order-1", "KTOS  260814C00065000", "sell", "opening", "200", 1, strike="65"
            ),
        ),
        daily_bars=({"symbol": "KTOS", "trade_date": date(2026, 8, 1), "close": D("70")},),
    )[0]
    assert otm.strike_upside_percent == D("8.33")
    assert itm.strike_upside_percent == D("-7.14")


def test_unknown_position_effect_and_equity_fills_are_not_tickets() -> None:
    rows = (
        _execution(
            "ghost",
            "order-x",
            "KTOS  260814C00065000",
            "sell",
            "unknown",
            "200",
            1,
            strike="65",
        ),
        {
            **_execution(
                "stock",
                "order-y",
                "KTOS",
                "sell",
                "opening",
                "1000",
                1,
                strike="0",
                underlying="KTOS",
            ),
            "asset_type": "equity",
        },
    )
    assert _project(rows) == ()


def test_empty_ledger_projects_no_tickets() -> None:
    assert _project(()) == ()


def test_accounts_do_not_consume_each_other() -> None:
    rows = (
        _execution(
            "open-a",
            "order-a",
            "KTOS  260814C00065000",
            "sell",
            "opening",
            "200",
            1,
            strike="65",
            account_mask="...1111",
        ),
        _execution(
            "close-b",
            "order-b",
            "KTOS  260814C00065000",
            "buy",
            "closing",
            "-50",
            2,
            strike="65",
            account_mask="...2222",
        ),
    )
    tickets = _project(rows)
    assert len(tickets) == 1
    assert tickets[0].record_id == "...1111:open-a"
    assert tickets[0].outcome == "Open"
    assert tickets[0].buyback_cost == D("0")


def test_demo_tickets_stay_authored_and_default_to_calls() -> None:
    snapshot = DemoDashboardReader().execute()
    assert len(snapshot.call_history) == 17
    assert {record.option_side for record in snapshot.call_history} == {"CALL"}
    assert any(record.sale_signal for record in snapshot.call_history)
    assert any(record.outcome == "Rolled" for record in snapshot.call_history)


def test_call_ledger_copy_is_honest_for_demo_and_live() -> None:
    snapshot = DemoDashboardReader().execute()
    demo_html = templates.env.get_template("partials/_call_ledger.html").render(snapshot=snapshot)
    assert "<h2>Option activity</h2>" in demo_html
    assert "Covered-call activity" not in demo_html
    assert "STRIKES TESTED 15\u201340% OTM" in demo_html
    assert "<small>C</small>" in demo_html
    assert "No covered-call executions" not in demo_html

    empty = templates.env.get_template("partials/_call_ledger.html").render(
        snapshot=replace(snapshot, mode="live", call_history=()),
    )
    assert "<h2>Option activity</h2>" in empty
    assert "STRIKES TESTED 15\u201340% OTM" not in empty
    assert "No short-option openings normalized." in empty

    put = _project(
        (
            _execution(
                "put-open",
                "put-1",
                "URNM  260918P00050000",
                "sell",
                "opening",
                "120",
                1,
                strike="50",
                expires=date(2026, 9, 18),
                option_side="put",
                underlying="URNM",
            ),
        ),
        daily_bars=({"symbol": "URNM", "trade_date": date(2026, 8, 1), "close": D("48")},),
    )
    put_html = templates.env.get_template("partials/_call_ledger.html").render(
        snapshot=replace(snapshot, mode="live", call_history=put)
    )
    assert "<small>P</small>" in put_html
    assert "STRIKES TESTED 15\u201340% OTM" not in put_html
    assert "-4.2%" in put_html
    assert 'class="numeric negative"' in put_html
    assert ">+4.2%" not in put_html
    assert ">—</small>" in put_html


def _project(
    executions: tuple[dict[str, object], ...],
    *,
    lifecycle: tuple[dict[str, object], ...] = (),
    daily_bars: tuple[dict[str, object], ...] = (),
):
    return project_call_sale_records(
        executions,
        lifecycle,
        daily_bars=daily_bars,
        as_of=AS_OF,
    )


def _execution(
    key: str,
    order: str,
    symbol: str,
    side: str,
    effect: str,
    net_cash: str,
    day: int,
    *,
    quantity: int = 1,
    strike: str = "65",
    expires: date = date(2026, 8, 14),
    option_side: str = "call",
    underlying: str = "KTOS",
    account_mask: str = "",
) -> dict[str, object]:
    cash = D(net_cash)
    payload: dict[str, object] = {
        "external_key": key,
        "order_external_key": order,
        "occurred_at": datetime(2026, 8, day, 15, tzinfo=UTC),
        "side": side,
        "position_effect": effect,
        "net_cash": cash,
        "gross_amount": abs(cash),
        "fees": D("0"),
        "quantity": D(quantity),
        "asset_type": "option",
        "symbol": symbol,
        "underlying_symbol": underlying,
        "option_side": option_side,
        "strike": D(strike),
        "expiration_date": expires,
        "contract_multiplier": D("100"),
    }
    if account_mask:
        payload["account_mask"] = account_mask
    return payload
