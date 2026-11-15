from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from trojanbites_extract.settings import get_settings
from trojanbites_extract.store.models import Base


def _ensure_sqlite_dir(url: str) -> None:
    if url.startswith("sqlite:///"):
        path = Path(url.replace("sqlite:///", "", 1))
        if not path.is_absolute():
            path = get_settings().root / path
        path.parent.mkdir(parents=True, exist_ok=True)


def get_engine(database_url: str | None = None):
    url = database_url or get_settings().database_url
    _ensure_sqlite_dir(url)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, future=True, connect_args=connect_args)


SessionLocal: sessionmaker[Session] | None = None


def migrate_schema(engine) -> None:
    """Lightweight SQLite migrations for additive columns/tables."""
    with engine.begin() as conn:
        Base.metadata.create_all(conn)
        # restaurants.campus_id / university_id may be missing on older DBs
        cols = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(restaurants)")).fetchall()
        }
        if "campus_id" not in cols:
            conn.execute(text("ALTER TABLE restaurants ADD COLUMN campus_id VARCHAR(64)"))
        if "university_id" not in cols:
            conn.execute(
                text("ALTER TABLE restaurants ADD COLUMN university_id VARCHAR(64)")
            )


def init_db(database_url: str | None = None) -> sessionmaker[Session]:
    global SessionLocal
    engine = get_engine(database_url)
    migrate_schema(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=True, autocommit=False, future=True)
    return SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    if SessionLocal is None:
        init_db()
    assert SessionLocal is not None
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
