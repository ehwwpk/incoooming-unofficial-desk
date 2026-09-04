from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

APP_ID = "incoooming-local-desk"
APP_VERSION = "0.1.0"
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
FINGERPRINT_SUFFIXES = {".css", ".html", ".js", ".py", ".svg"}


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    app: str
    version: str
    pid: int
    started_at: str
    build_id: str

    def as_dict(self) -> dict[str, str | int]:
        return asdict(self)


def current_build_id() -> str:
    """Hash executable application assets so a launcher can spot a stale server."""

    digest = hashlib.sha256()
    source_migrations = PACKAGE_ROOT.parents[1] / "migrations"
    packaged_migrations = PACKAGE_ROOT / "migrations"
    roots = (
        PACKAGE_ROOT,
        source_migrations if source_migrations.is_dir() else packaged_migrations,
    )
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(
            item
            for item in root.rglob("*")
            if item.is_file()
            and item.suffix.lower() in FINGERPRINT_SUFFIXES
            and "__pycache__" not in item.parts
        ):
            digest.update(f"{root.name}/{path.relative_to(root).as_posix()}".encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def new_runtime_identity() -> RuntimeIdentity:
    return RuntimeIdentity(
        app=APP_ID,
        version=APP_VERSION,
        pid=os.getpid(),
        started_at=datetime.now(UTC).isoformat(),
        build_id=current_build_id(),
    )
