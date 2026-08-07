from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

SessionFactory = sessionmaker[Session]


def ensure_sqlite_parent(database_url: str) -> None:
    prefix = "sqlite+pysqlite:///"
    if database_url.startswith(prefix):
        database_path = Path(database_url.removeprefix(prefix))
        database_path.parent.mkdir(parents=True, exist_ok=True)


def create_database_engine(database_url: str) -> Engine:
    ensure_sqlite_parent(database_url)
    engine = create_engine(
        database_url,
        future=True,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
    )

    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _configure_sqlite(dbapi_connection: object, connection_record: object) -> None:
            del connection_record
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> SessionFactory:
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False, future=True)
