from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from schwab_dashboard.web.rendering import templates

LOGGER = logging.getLogger(__name__)


async def unhandled_exception(request: Request, exc: Exception) -> Response:
    """Return a useful local recovery surface without leaking exception details."""

    LOGGER.exception("Unhandled request failure", exc_info=exc)
    if "text/html" not in request.headers.get("accept", ""):
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "detail": "The local desk hit an unexpected error. Check server health and logs.",
            },
        )
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        status_code=500,
        context={"request_path": request.url.path},
    )
