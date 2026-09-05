from __future__ import annotations

from fastapi.testclient import TestClient

from schwab_dashboard.app import create_app

POSITIONS = (
    b"Account,Symbol,Description,Quantity,Last Price,Market Value,Average Price\n"
    b"Brokerage 4321,CVX,Chevron Corp,100,195.00,19500.00,150.00\n"
    b"Brokerage 4321,CVX  260821C00205000,CVX 08/21/2026 205 Call,-1,1.25,-125,2\n"
)
ACTIVITY = (
    b"Account,Date,Action,Symbol,Description,Quantity,Price,Fees,Amount\n"
    b"Brokerage 4321,08/01/2026,Sell to Open,CVX  260821C00205000,"
    b"CVX 08/21/2026 205 Call,1,1.25,0.03,124.97\n"
    b"Brokerage 4321,08/02/2026,Dividend,CVX,Chevron dividend,,,,171.00\n"
)
UNSAFE_ACTIVITY = (
    b"Account,Date,Action,Symbol,Description,Quantity,Price,Amount\n"
    b"Brokerage 4321,08/03/2026,Sell,CVX,private memo,private-number,10,10\n"
    b"Brokerage 4321,08/04/2026,Dividend,CVX,Dividend,,,25\n"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    with TestClient(create_app(), base_url="http://127.0.0.1:8182") as client:
        gateway = client.get("/sources")
        require(gateway.status_code == 200, "installed source gateway did not render")
        require(
            gateway.text.count("/static/incoooming-operators.png") == 2,
            "installed source gateway did not reference both operator images",
        )

        operator_art = client.get("/static/incoooming-operators.png")
        require(operator_art.status_code == 200, "installed operator artwork was not served")
        require(
            operator_art.headers["content-type"] == "image/png",
            "installed operator artwork did not use the PNG content type",
        )
        require(
            operator_art.content.startswith(b"\x89PNG\r\n\x1a\n"),
            "installed operator artwork was not a PNG",
        )

        unsafe_preview = client.post(
            "/sources/csv/preview",
            data={"dataset_name": "Installed redaction smoke", "broker": "generic"},
            files=[("files", ("unsafe.csv", UNSAFE_ACTIVITY, "text/csv"))],
        )
        require(unsafe_preview.status_code == 200, "installed redaction preview failed")
        unsafe_payload = unsafe_preview.json()
        require(
            unsafe_payload["files"][0]["issues"][0]["reason"]
            == "number [source value] is not a valid broker number",
            "installed preview did not sanitize a rejected source value",
        )
        require("private-number" not in unsafe_preview.text, "installed preview echoed source data")

        uploads = [
            ("files", ("positions.csv", POSITIONS, "text/csv")),
            ("files", ("activity.csv", ACTIVITY, "text/csv")),
        ]
        preview = client.post(
            "/sources/csv/preview",
            data={"dataset_name": "Installed CSV smoke", "broker": "generic"},
            files=uploads,
        )
        require(preview.status_code == 200, "installed CSV preview failed")
        preview_payload = preview.json()
        require(preview_payload["ok"] is True, "installed CSV preview was not committable")
        require(
            preview_payload["counts"]["positions"] == 2
            and preview_payload["counts"]["activity"] == 2,
            "installed CSV preview counts changed",
        )
        require(
            set(preview_payload["capabilities"])
            == {"positions", "executions", "cash_movements", "dividends"},
            "installed CSV capabilities changed",
        )

        imported = client.post(
            "/sources/csv",
            data={
                "dataset_name": "Installed CSV smoke",
                "broker": "generic",
                "preview_fingerprint": preview_payload["fingerprint"],
            },
            files=uploads,
            follow_redirects=False,
        )
        require(imported.status_code == 303, "installed CSV commit failed")
        require(imported.headers["location"] == "/", "installed CSV redirect changed")

        csv_pages = {
            "desk": client.get("/"),
            "risk": client.get("/workspaces/risk"),
            "results": client.get("/workspaces/attribution"),
            "radar": client.get("/workspaces/radar"),
            "records": client.get("/workspaces/records"),
            "chart": client.get("/api/v1/charts/CVX"),
        }
        for label, response in csv_pages.items():
            require(response.status_code == 200, f"installed CSV {label} did not render")
        require('data-demo-mode="false"' in csv_pages["desk"].text, "CSV mode marker missing")
        require("CSV BOOK" in csv_pages["desk"].text, "CSV disclosure missing")
        require(
            "The date above is import time, not a broker valuation time" in csv_pages["desk"].text,
            "CSV import-time disclosure missing",
        )
        require(
            "data-performance-comparison-payload" not in csv_pages["results"].text,
            "CSV book invented a benchmark return path",
        )
        csv_api = client.get("/api/v1/dashboard")
        require(csv_api.status_code == 200, "installed CSV dashboard API failed")
        csv_payload = csv_api.json()
        require(csv_payload["mode"] == "csv", "installed CSV API mode changed")
        require(
            csv_payload["portfolio"]["total_value"] == "19375.00",
            "installed CSV position value changed",
        )
        require(csv_payload["risk"]["daily_theta"] is None, "CSV invented option theta")
        csv_calls = csv_payload["live_position_book"]["calls"]
        require(len(csv_calls) == 1, "installed CSV option inventory changed")
        require(
            all(
                csv_calls[0][field] is None
                for field in ("implied_volatility_percent", "delta", "gamma", "theta_per_share")
            ),
            "CSV invented IV or Greeks",
        )

        volatility = client.get("/workspaces/volatility", follow_redirects=False)
        require(volatility.status_code == 303, "legacy Volatility route did not redirect")
        require(
            volatility.headers["location"].endswith("/workspaces/radar"),
            "legacy Volatility route did not land on Radar",
        )

        selection = client.post(
            "/sources/select",
            data={"source_key": "demo"},
            follow_redirects=False,
        )
        require(selection.status_code == 303, "installed demo source could not be selected")
        require(selection.headers["location"] == "/", "installed demo redirect changed")

        dashboard = client.get("/")
        require(dashboard.status_code == 200, "installed demo dashboard did not render")
        require('data-demo-mode="true"' in dashboard.text, "demo mode marker is missing")
        require("SIMULATED DATA" in dashboard.text, "simulated-data disclosure is missing")
        require(
            "Fictional positions and contract quotes, IV, and Greeks" in dashboard.text,
            "fictional market-data disclosure is missing",
        )

        demo_pages = {
            "risk": client.get("/workspaces/risk"),
            "results": client.get("/workspaces/attribution"),
            "radar": client.get("/workspaces/radar"),
            "records": client.get("/workspaces/records"),
            "chart": client.get("/api/v1/charts/CVX"),
            "catalog": client.get("/api/v1/workspaces"),
        }
        for label, response in demo_pages.items():
            require(response.status_code == 200, f"installed demo {label} did not render")
        demo_api = client.get("/api/v1/dashboard")
        require(demo_api.status_code == 200, "installed demo dashboard API failed")
        demo_payload = demo_api.json()
        require(demo_payload["mode"] == "demo", "installed demo API mode changed")
        require(demo_payload["as_of"].startswith("2026-08-07"), "demo date changed")
        clocks = [
            clock
            for underlying in demo_payload["underlyings"]
            for clock in underlying["open_call_clocks"]
        ]
        cvx_195 = next(
            (clock for clock in clocks if clock["strike"] == "195"),
            None,
        )
        require(cvx_195 is not None, "installed demo CVX 195 call is missing")
        require(
            cvx_195["implied_volatility_percent"] == "24.5"
            and cvx_195["delta"] == "0.31"
            and cvx_195["gamma"] == "0.052"
            and cvx_195["theta_per_share"] == "-0.080"
            and cvx_195["vega"] == "0.061",
            "installed demo IV or Greeks changed",
        )
        require(
            cvx_195["quote_status"] == "SIMULATED",
            "installed demo quote provenance is not explicit",
        )


if __name__ == "__main__":
    main()
