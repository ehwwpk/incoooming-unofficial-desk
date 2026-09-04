from __future__ import annotations

from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; base-uri 'none'; connect-src 'self'; font-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; img-src 'self' data:; "
        "object-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'"
    ),
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


class LocalRequestSecurityMiddleware:
    """Protect the local, unauthenticated UI from browser cross-site requests."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if scope["method"].upper() in UNSAFE_METHODS and not _safe_browser_source(scope, headers):
            response = PlainTextResponse("Cross-site request blocked.", status_code=403)
            await response(scope, receive, _security_header_sender(scope, send))
            return

        await self.app(scope, receive, _security_header_sender(scope, send))


def _security_header_sender(scope: Scope, send: Send) -> Send:
    async def send_with_headers(message: Message) -> None:
        if message["type"] == "http.response.start":
            response_headers = MutableHeaders(scope=message)
            for name, value in SECURITY_HEADERS.items():
                response_headers.setdefault(name, value)
            if not str(scope.get("path", "")).startswith("/static/"):
                response_headers.setdefault("Cache-Control", "no-store")
        await send(message)

    return send_with_headers


def _safe_browser_source(scope: Scope, headers: Headers) -> bool:
    fetch_site = headers.get("sec-fetch-site", "").casefold()
    if fetch_site and fetch_site not in {"same-origin", "none"}:
        return False

    source = headers.get("origin") or headers.get("referer")
    if source is None:
        # Non-browser API clients do not send browser origin metadata.
        return True
    return _origin(source) == _request_origin(scope, headers)


def _request_origin(scope: Scope, headers: Headers) -> tuple[str, str, int] | None:
    scheme = str(scope.get("scheme", "http")).casefold()
    return _origin(f"{scheme}://{headers.get('host', '')}")


def _origin(value: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(value)
        if parsed.scheme.casefold() not in {"http", "https"} or parsed.hostname is None:
            return None
        port = parsed.port or (443 if parsed.scheme.casefold() == "https" else 80)
    except ValueError:
        return None
    return parsed.scheme.casefold(), parsed.hostname.casefold(), port
