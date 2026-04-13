"""
Unit test configuration.
"""
import os
import tempfile

_DB_FILE = os.path.join(tempfile.gettempdir(), "lifeshield_unit_tests.sqlite3")
if os.path.exists(_DB_FILE):
    os.unlink(_DB_FILE)

os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE}"
os.environ["APP_ENV"] = "test"
os.environ["BUREAU_SANDBOX_MODE"] = "true"

import pytest
from sqlalchemy import create_engine, inspect as sa_inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_TEST_ENGINE = None
_SESSION_FACTORY = None


def _build_test_db(engine):
    """
    Create all tables and indexes safely.

    The challenge: SQLAlchemy's table.create(checkfirst=True) still tries to
    CREATE the table's indexes even if the table already exists, causing
    'already exists' errors on SQLite. Solution: check existence ourselves
    and only create tables that don't exist yet; skip index creation for
    tables that already exist.
    """
    from app.core.database import Base
    from sqlalchemy.schema import CreateTable, CreateIndex
    import app.models.user           # noqa: F401
    import app.models.agent          # noqa: F401
    import app.models.client         # noqa: F401
    import app.models.dispute        # noqa: F401
    import app.models.communication  # noqa: F401
    import app.models.billing        # noqa: F401
    import app.models.audit          # noqa: F401
    import app.models.compliance     # noqa: F401
    import app.models.document       # noqa: F401
    import app.models.appointment    # noqa: F401

    insp = sa_inspect(engine)
    existing_tables = set(insp.get_table_names())

    # Collect all existing index names
    existing_indexes = set()
    for tname in existing_tables:
        for idx_info in insp.get_indexes(tname):
            if idx_info.get("name"):
                existing_indexes.add(idx_info["name"])

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name in existing_tables:
                continue  # Table exists — skip entirely (avoids index re-creation)

            # Create the table
            conn.execute(CreateTable(table))

            # Create indexes for this new table
            for idx in table.indexes:
                if idx.name not in existing_indexes:
                    conn.execute(CreateIndex(idx))
                    existing_indexes.add(idx.name)


def _ensure_engine():
    global _TEST_ENGINE, _SESSION_FACTORY

    if _TEST_ENGINE is not None:
        return _TEST_ENGINE

    _TEST_ENGINE = create_engine(
        f"sqlite:///{_DB_FILE}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    _build_test_db(_TEST_ENGINE)

    _SESSION_FACTORY = sessionmaker(
        bind=_TEST_ENGINE,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    import app.core.database as db_module
    db_module.engine = _TEST_ENGINE
    db_module.SessionLocal = _SESSION_FACTORY

    return _TEST_ENGINE


@pytest.fixture(scope="session")
def shared_engine():
    return _ensure_engine()


@pytest.fixture
def db(shared_engine):
    """Per-test session with SAVEPOINT rollback."""
    _ensure_engine()
    session = _SESSION_FACTORY()
    session.begin_nested()
    yield session
    session.rollback()
    session.close()
