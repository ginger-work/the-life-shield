"""
Unit test configuration.
Sets environment variables BEFORE app modules are imported.
"""
import os

# Override DATABASE_URL so app.core.database uses SQLite (no PostgreSQL needed)
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["APP_ENV"] = "test"
os.environ["BUREAU_SANDBOX_MODE"] = "true"

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def _create_tables_safe(engine) -> None:
    """
    Create all SQLAlchemy tables and indexes, gracefully skipping
    items that already exist (handles SQLite's lack of IF NOT EXISTS on indexes).
    """
    from app.core.database import Base
    import app.models.user          # noqa
    import app.models.agent         # noqa
    import app.models.client        # noqa
    import app.models.dispute       # noqa
    import app.models.communication  # noqa
    import app.models.billing        # noqa
    import app.models.audit          # noqa
    import app.models.compliance     # noqa
    import app.models.document       # noqa
    import app.models.appointment    # noqa

    # Create tables (checkfirst=True handles tables but not all indexes)
    Base.metadata.create_all(engine, checkfirst=True)


@pytest.fixture(scope="session", autouse=True)
def _setup_test_db():
    """Create the shared test database once per test session."""
    # Import and patch the engine before any test module uses it
    engine = create_engine(
        "sqlite:///file:unit_test_shared?mode=memory&cache=shared",
        connect_args={"check_same_thread": False, "uri": True},
        poolclass=StaticPool,
    )

    try:
        _create_tables_safe(engine)
    except Exception as e:
        if "already exists" in str(e):
            pass  # Tables/indexes already created — fine
        else:
            raise

    # Patch app.core.database.engine to use our test engine
    import app.core.database as db_module
    original_engine = db_module.engine
    original_session = db_module.SessionLocal

    db_module.engine = engine
    db_module.SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    yield engine

    db_module.engine = original_engine
    db_module.SessionLocal = original_session
    engine.dispose()


@pytest.fixture(scope="session")
def shared_engine(_setup_test_db):
    """Return the shared test engine."""
    return _setup_test_db


@pytest.fixture
def db(shared_engine):
    """
    Provide a transactional DB session that rolls back after each test.
    Keeps tests isolated without re-creating tables.
    """
    connection = shared_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()
