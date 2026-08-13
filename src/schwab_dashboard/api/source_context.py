from __future__ import annotations

from fastapi import Request

SOURCE_COOKIE = "incoooming_source"


def selected_source_key(request: Request) -> str | None:
    value = request.cookies.get(SOURCE_COOKIE, "").strip()
    if value in {"schwab", "demo"} or value.startswith("csv:"):
        return value
    return None


def source_label(source_key: str | None, *, dataset_name: str | None = None) -> str:
    if source_key == "demo":
        return "Demo book"
    if source_key and source_key.startswith("csv:"):
        return dataset_name or "CSV book"
    return "Schwab live"
