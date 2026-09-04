from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from schwab_dashboard.api.dependencies import get_container
from schwab_dashboard.api.source_context import SOURCE_COOKIE, selected_source_key
from schwab_dashboard.application.imports import CsvImportError
from schwab_dashboard.application.imports.csv_text import MAX_CSV_BYTES
from schwab_dashboard.container import Container
from schwab_dashboard.domain.data_source import BrokerKind
from schwab_dashboard.web.rendering import templates

router = APIRouter(tags=["sources"])
ContainerDependency = Annotated[Container, Depends(get_container)]


@router.get("/sources", response_class=HTMLResponse)
def source_gateway(request: Request, container: ContainerDependency) -> HTMLResponse:
    return _render_gateway(request, container)


@router.post("/sources/select")
def select_source(
    container: ContainerDependency,
    source_key: Annotated[str, Form()],
) -> RedirectResponse:
    if source_key == "schwab":
        pass
    elif source_key == "demo":
        pass
    elif source_key.startswith("csv:"):
        dataset_id = source_key.removeprefix("csv:")
        if container.source_store.get_dataset(dataset_id) is None:
            raise HTTPException(status_code=404, detail="CSV dataset not found")
    else:
        raise HTTPException(status_code=422, detail="Unsupported data source")
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        SOURCE_COOKIE,
        source_key,
        max_age=31_536_000,
        httponly=True,
        samesite="lax",
    )
    return response


@router.post("/sources/csv", response_class=HTMLResponse)
async def import_csv_source(
    request: Request,
    container: ContainerDependency,
    dataset_name: Annotated[str, Form()],
    broker: Annotated[BrokerKind, Form()],
    files: Annotated[list[UploadFile], File()],
    preview_fingerprint: Annotated[str, Form()],
) -> Response:
    try:
        payloads = await _read_csv_uploads(files)
        dataset = container.import_csv_dataset().execute(
            name=dataset_name,
            broker=broker,
            files=tuple(payloads),
            preview_fingerprint=preview_fingerprint,
        )
    except (CsvImportError, ValueError) as exc:
        return _render_gateway(request, container, error=str(exc), status_code=422)
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        SOURCE_COOKIE,
        f"csv:{dataset.id}",
        max_age=31_536_000,
        httponly=True,
        samesite="lax",
    )
    return response


@router.post("/sources/csv/preview")
async def preview_csv_source(
    container: ContainerDependency,
    dataset_name: Annotated[str, Form()],
    broker: Annotated[BrokerKind, Form()],
    files: Annotated[list[UploadFile], File()],
) -> JSONResponse:
    try:
        payloads = await _read_csv_uploads(files)
        preview = container.import_csv_dataset().preview(
            name=dataset_name,
            broker=broker,
            files=tuple(payloads),
        )
    except (CsvImportError, ValueError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=422)
    return JSONResponse(
        {
            "ok": True,
            "fingerprint": preview.fingerprint,
            "can_commit": preview.can_commit,
            "counts": {
                "positions": preview.position_count,
                "activity": preview.activity_count,
                "ignored": preview.ignored_count,
                "review": preview.review_count,
                "rejected": preview.rejected_count,
            },
            "capabilities": preview.capabilities,
            "warnings": preview.warnings,
            "files": [
                {
                    "name": file.filename,
                    "profile": file.profile,
                    "broker": file.detected_broker.value,
                    "confidence": file.confidence,
                    "kind": file.file_kind,
                    "header_row": file.header_row,
                    "encoding": file.encoding,
                    "delimiter": "TAB" if file.delimiter == "\t" else file.delimiter,
                    "imported": file.imported_count,
                    "ignored": file.ignored_count,
                    "review": file.review_count,
                    "rejected": file.rejected_count,
                }
                for file in preview.files
            ],
        }
    )


async def _read_csv_uploads(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    if len(files) > 8:
        raise CsvImportError("Import no more than eight CSV files at once.")
    payloads: list[tuple[str, bytes]] = []
    for file in files:
        raw_name = (file.filename or "import.csv").strip()
        filename = raw_name.replace("\\", "/").rsplit("/", 1)[-1]
        if not filename or len(filename) > 255 or any(ord(char) < 32 for char in filename):
            raise CsvImportError("Each CSV needs a plain file name of 255 characters or fewer.")
        content = await file.read(MAX_CSV_BYTES + 1)
        if len(content) > MAX_CSV_BYTES:
            raise CsvImportError("CSV files are limited to 10 MB each.")
        payloads.append((filename, content))
    return payloads


@router.get("/sources/templates/{template_kind}.csv")
def csv_template(template_kind: str) -> Response:
    templates_by_kind = {
        "positions": (
            "Account,Symbol,Description,Quantity,Last Price,Market Value,"
            "Average Price,Day Change P&L\n"
            "...1234,CVX,Chevron Corp,100,195.00,19500.00,150.00,125.00\n"
        ),
        "activity": (
            "Account,Date,Action,Symbol,Description,Quantity,Price,Fees,Amount\n"
            "...1234,08/01/2026,Sell to Open,"
            "CVX  260821C00205000,CVX 08/21/2026 205 Call,1,1.25,0.03,124.97\n"
        ),
    }
    body = templates_by_kind.get(template_kind)
    if body is None:
        raise HTTPException(status_code=404, detail="CSV template not found")
    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="incoooming-{template_kind}.csv"'},
    )


def _render_gateway(
    request: Request,
    container: Container,
    *,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="sources.html",
        status_code=status_code,
        context={
            "datasets": container.source_store.list_datasets(),
            "selected_source": selected_source_key(request),
            "schwab_credentials_configured": container.settings.schwab_credentials_configured,
            "schwab_token_available": container.token_available(),
            "error": error,
        },
    )
