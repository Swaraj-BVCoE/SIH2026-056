"""
db/database.py
───────────────
SQLAlchemy engine, session factory, and lifecycle helpers.

Usage:
    from db.database import get_db, init_db

    # In startup:
    init_db()

    # In a scraper/pipeline function:
    with get_db() as session:
        session.add(flight_price_obj)
        session.commit()
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from loguru import logger
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from config.settings import settings
from db.models import Base

# ── Engine ───────────────────────────────────────────────────────────────────
_connect_args: dict = {}
if settings.database_url.startswith("sqlite"):
    # Enable WAL mode and foreign keys for SQLite
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    echo=False,          # Set True for SQL query debug logging
    pool_pre_ping=True,  # Re-validates connections before use
)


# ── SQLite-specific pragmas ───────────────────────────────────────────────────
@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record):
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")   # Better concurrent reads
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL") # Balanced durability/speed
        cursor.close()


# ── Session factory ──────────────────────────────────────────────────────────
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # Keep objects usable after commit
)


# ── Public helpers ───────────────────────────────────────────────────────────
def init_db() -> None:
    """
    Create all tables defined in models.py if they don't already exist.
    Safe to call on every startup (idempotent).
    """
    logger.info("Initializing database at: {}", settings.database_url)
    Base.metadata.create_all(bind=engine)
    logger.success("Database tables created / verified.")


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Context manager that yields a SQLAlchemy Session.
    Automatically commits on success, rolls back on exception.

    Example:
        with get_db() as db:
            db.add(record)
    """
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI dependency. Unlike ``get_db`` this is a plain generator."""
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def health_check() -> bool:
    """Returns True if the database is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("DB health check failed: {}", exc)
        return False
