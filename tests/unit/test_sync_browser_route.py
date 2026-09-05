from types import SimpleNamespace

from starlette.requests import Request

from schwab_dashboard.api.routes.dashboard import sync_from_browser


class _FailingContainer:
    settings = SimpleNamespace(demo_mode=False)

    def sync_full(self, *, trigger: str) -> None:
        assert trigger == "browser"
        raise ValueError("normalized market timestamp rejected")


def test_browser_sync_failure_redirects_to_the_dashboard_instead_of_returning_500() -> None:
    request = Request({"type": "http", "headers": []})
    response = sync_from_browser(request, _FailingContainer())  # type: ignore[arg-type]

    assert response.status_code == 303
    assert response.headers["location"] == "/?sync=failed"
