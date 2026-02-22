"""
db/session.py
--------------
SQLAlchemy async engine + session factory.

Uses aiosqlite as the default local driver (zero-config) and PostgreSQL
(asyncpg) when DATABASE_URL starts with "postgresql".

The module exposes:
  - ``engine``          — SQLAlchemy async engine
  - ``AsyncSessionLocal``— async session factory
  - ``Base``            — declarative base for ORM models
  - ``get_db()``        — FastAPI dependency yielding a session per request
  - ``create_all_tables()``— called from main.py startup event

Environment variable
────────────────────
  DATABASE_URL   (from .env / config/settings.py)

  Not set / falsy  →  sqlite+aiosqlite:///./koda.db  (default, no setup needed)
  postgresql://... →  postgresql+asyncpg://...

Schema creation
───────────────
Tables are created automatically via ``create_all_tables()`` so you don't
need to run migrations for the initial SQLite dev setup.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Import the shared DeclarativeBase — do NOT define a second Base here
from db.base import Base  # noqa: F401  (re-exported so session importers still get it)

log = logging.getLogger(__name__)

# ── Resolve DB URL ─────────────────────────────────────────────────────────────

def _resolve_url() -> str:
    try:
        from config.settings import settings
        url = getattr(settings, "DATABASE_URL", None)
    except Exception:
        url = None

    if not url:
        log.info("DATABASE_URL not set — using local SQLite (koda.db)")
        return "sqlite+aiosqlite:///./koda.db"

    # If the user passes a plain postgres URL, swap driver to asyncpg
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)

    return url


_DB_URL = _resolve_url()

# ── Engine ─────────────────────────────────────────────────────────────────────

_connect_args = {"check_same_thread": False} if "sqlite" in _DB_URL else {}

engine = create_async_engine(
    _DB_URL,
    echo=False,           # set True to log SQL (noisy in prod)
    pool_pre_ping=True,
    connect_args=_connect_args,
)

# ── Sync engine (used by Celery workers that can't run async) ──────────────────

def _sync_url(url: str) -> str:
    """Convert an async DB URL to its synchronous driver equivalent."""
    return (
        url
        .replace("sqlite+aiosqlite://", "sqlite://")
        .replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    )

from sqlalchemy import create_engine as _create_sync_engine
from sqlalchemy.orm import sessionmaker

sync_engine = _create_sync_engine(
    _sync_url(_DB_URL),
    pool_pre_ping=True,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(
    bind=sync_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

# ── Session factory ────────────────────────────────────────────────────────────

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ── FastAPI dependency ─────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a SQLAlchemy async session for the duration of a request.

    Usage in an endpoint::

        async def my_endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

# ── Startup helper ─────────────────────────────────────────────────────────────

async def create_all_tables() -> None:
    """Create all ORM-mapped tables (idempotent — safe to call on every startup)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("Database tables created/verified  url=%s", _DB_URL.split("@")[-1])
