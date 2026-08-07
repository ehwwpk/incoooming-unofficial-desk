from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from schwab_dashboard.infrastructure.database.engine import (
    create_database_engine,
    create_session_factory,
)
from schwab_dashboard.infrastructure.database.tables import Base
from schwab_dashboard.infrastructure.database.uow import build_uow_factory


@pytest.fixture()
def database_runtime(tmp_path: Path) -> Iterator[tuple[object, object, object]]:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'test.sqlite3').as_posix()}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    uow_factory = build_uow_factory(session_factory)
    yield engine, session_factory, uow_factory
    engine.dispose()
