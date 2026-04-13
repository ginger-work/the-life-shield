"""
Database engine, session management, and base model.
Uses SQLAlchemy 2.0 with connection pooling.
"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# SQLAlchemy Engine
# ---------------------------------------------------------------------------

def _build_engine_kwargs() -> dict:
    """Build engine kwargs based on environment."""
    kwargs = {
        "echo": settings.DATABASE_ECHO,
        "echo_pool": False,
        "future": True,
    }

    # Use NullPool in test environments to avoid connection issues
    if settings.APP_ENV == "test":
        kwargs["poolclass"] = NullPool
    else:
        kwargs.update({
            "pool_size": settings.DATABASE_POOL_SIZE,
            "max_overflow": settings.DATABASE_MAX_OVERFLOW,
            "pool_timeout": settings.DATABASE_POOL_TIMEOUT,
            "pool_pre_ping": True,   # Verify connections before use
            "pool_recycle": 3600,    # Recycle connections after 1 hour
        })

    return kwargs


engine = create_engine(settings.DATABASE_URL, **_build_engine_kwargs())


# ---------------------------------------------------------------------------
# Session Factory
# ---------------------------------------------------------------------------

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# Declarative Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy models.
    Provides common functionality and type annotations.
    """
    pass


# ---------------------------------------------------------------------------
# Dependency Injection Helper (FastAPI)
# ---------------------------------------------------------------------------

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session.
    Automatically closes the session when the request is done.

    Usage in route:
        @router.get("/items")
        def get_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Context manager for database sessions outside of FastAPI request lifecycle.
    Use for background tasks, scripts, and tests.

    Usage:
        with get_db_context() as db:
            user = db.query(User).first()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

def check_database_health() -> dict:
    """
    Verify database connectivity. Used in /health endpoint.
    Returns dict with status and details.
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1 AS health_check"))
            row = result.fetchone()
            if row and row[0] == 1:
                return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return {"status": "unhealthy", "database": str(e)}

    return {"status": "unknown", "database": "no response"}
