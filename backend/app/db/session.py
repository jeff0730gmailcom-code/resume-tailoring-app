"""SQLAlchemy engine/session setup for the SQLite database.

Sync SQLAlchemy (not the async variant) is used deliberately: SQLite has no
real concurrent-connection benefit from async drivers, and every call site
in this project already follows the established "wrap blocking work in
asyncio.to_thread" pattern used elsewhere (see app/services/docx_to_pdf.py) -
introducing a second, async-only DB access style would be inconsistent for
no real gain at this scale.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.models import Base

# check_same_thread=False: FastAPI may run a request's sync DB calls (via
# asyncio.to_thread) on a different thread than the one that created the
# engine - safe here since each request opens/closes its own short-lived
# Session (see session_scope) rather than sharing one across threads.
_engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create any missing tables. Safe to call on every startup - a no-op
    once the schema already exists. No Alembic migrations at this MVP
    stage; see app/db/__init__.py."""
    Base.metadata.create_all(bind=_engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional session: commits on success, rolls back and
    re-raises on any exception, always closes."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
