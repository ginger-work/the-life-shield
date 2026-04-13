"""
The Life Shield — pytest Configuration
Global fixtures, test database setup, and shared test utilities.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from faker import Faker
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# ── Force test environment before any app imports ──────────────────────────────
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars-long!")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/lifeshield_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")   # DB 15 = test isolation
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("BCRYPT_ROUNDS", "4")  # Speed up test hashing

from models.base import Base
from models.user import User, UserSession, AuditLog
from models.agent import AgentProfile, ClientAgentAssignment
from config.security import UserRole, settings

fake = Faker()
Faker.seed(42)


# ─────────────────────────────────────────────────────────────────────────────
# TEST DATABASE — SQLite in-memory (no external DB required for unit tests)
# ─────────────────────────────────────────────────────────────────────────────

TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def engine():
    """Create a shared SQLite engine for the test session."""
    eng = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Enable foreign key support for SQLite
    @event.listens_for(eng, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture(scope="session")
def session_factory(engine):
    """Session factory bound to the test engine."""
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture
def db(session_factory) -> Generator[Session, None, None]:
    """
    Provide a transactional DB session that rolls back after each test.
    This keeps tests isolated without dropping/recreating tables.
    """
    connection = session_factory.kw["bind"].connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ─────────────────────────────────────────────────────────────────────────────
# FACTORY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def make_user(
    db: Session,
    *,
    email: str | None = None,
    role: UserRole = UserRole.CLIENT,
    is_active: bool = True,
    is_verified: bool = True,
    hashed_password: str = "$2b$04$teststeststeststeststeststPASSWORDHASH123456",
    **kwargs,
) -> User:
    """Create and persist a User for testing."""
    user = User(
        id=uuid.uuid4(),
        email=email or fake.unique.email(),
        hashed_password=hashed_password,
        role=role,
        first_name=fake.first_name(),
        last_name=fake.last_name(),
        phone=f"+1{fake.numerify('##########')}",
        is_active=is_active,
        is_verified=is_verified,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        **kwargs,
    )
    db.add(user)
    db.flush()
    return user


def make_admin(db: Session, **kwargs) -> User:
    """Create an admin user."""
    return make_user(db, role=UserRole.ADMIN, **kwargs)


def make_agent_user(db: Session, **kwargs) -> User:
    """Create an agent-role user (the human account behind an AI agent)."""
    return make_user(db, role=UserRole.AGENT, **kwargs)


def make_agent_profile(
    db: Session,
    user: User | None = None,
    *,
    agent_name: str | None = None,
    display_name: str | None = None,
    role: str = "client_success_agent",
    is_active: bool = True,
    **kwargs,
) -> AgentProfile:
    """Create and persist an AgentProfile for testing."""
    agent = AgentProfile(
        id=uuid.uuid4(),
        user_id=user.id if user else None,
        agent_name=agent_name or fake.first_name() + " " + fake.last_name(),
        display_name=display_name or "Tim Shaw",
        role=role,
        tone="professional",
        communication_style="calm, empathetic, direct",
        is_active=is_active,
        is_accepting_clients=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        **kwargs,
    )
    db.add(agent)
    db.flush()
    return agent


def make_client_assignment(
    db: Session,
    client: User,
    agent: AgentProfile,
    *,
    is_active: bool = True,
    **kwargs,
) -> ClientAgentAssignment:
    """Create and persist a ClientAgentAssignment."""
    assignment = ClientAgentAssignment(
        id=uuid.uuid4(),
        client_user_id=client.id,
        agent_id=agent.id,
        is_active=is_active,
        assigned_at=datetime.now(timezone.utc),
        **kwargs,
    )
    db.add(assignment)
    db.flush()
    return assignment


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def client_user(db) -> User:
    """A standard active client user."""
    return make_user(db, role=UserRole.CLIENT)


@pytest.fixture
def admin_user(db) -> User:
    """An active admin user."""
    return make_admin(db)


@pytest.fixture
def agent_profile(db) -> AgentProfile:
    """An active AgentProfile (Tim Shaw)."""
    return make_agent_profile(db)


@pytest.fixture
def agent_profile_with_user(db) -> AgentProfile:
    """An AgentProfile linked to an agent-role user."""
    user = make_agent_user(db)
    return make_agent_profile(db, user=user, display_name="Tim Shaw")


@pytest.fixture
def client_with_agent(db) -> tuple[User, AgentProfile, ClientAgentAssignment]:
    """A client assigned to an agent."""
    client = make_user(db)
    agent = make_agent_profile(db)
    assignment = make_client_assignment(db, client, agent)
    return client, agent, assignment


@pytest.fixture
def valid_password() -> str:
    """A password that meets all policy requirements."""
    return "SecurePassw0rd!2026"


@pytest.fixture
def weak_passwords() -> list[str]:
    """A collection of passwords that fail various policy checks."""
    return [
        "",                   # empty
        "short",              # too short
        "alllowercase1!",     # no uppercase
        "ALLUPPERCASE1!",     # no lowercase
        "NoDigitsHere!!",     # no digits
        "NoSpecialChars12",   # no special chars
        "short1A!",           # too short
    ]
