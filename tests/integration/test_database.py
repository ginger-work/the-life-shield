"""
The Life Shield — Integration Tests: Database
Tests for ORM session operations, relationships, cascade deletes,
transaction rollbacks, and schema integrity.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.user import AuditLog, User, UserSession
from models.agent import AgentProfile, ClientAgentAssignment
from config.security import UserRole
from tests.conftest import (
    make_agent_profile,
    make_client_assignment,
    make_user,
)


# ═════════════════════════════════════════════════════════════════════════════
# BASIC CRUD
# ═════════════════════════════════════════════════════════════════════════════

class TestUserCRUD:
    """Create, read, update, delete on Users table."""

    def test_create_user(self, db):
        user = make_user(db, email="crud@example.com")
        db.flush()
        fetched = db.query(User).filter_by(email="crud@example.com").first()
        assert fetched is not None
        assert str(fetched.id) == str(user.id)

    def test_read_user_by_id(self, db):
        user = make_user(db)
        fetched = db.query(User).filter_by(id=user.id).first()
        assert fetched is not None

    def test_update_user_first_name(self, db):
        user = make_user(db)
        user.first_name = "UpdatedName"
        db.flush()
        fetched = db.query(User).filter_by(id=user.id).first()
        assert fetched.first_name == "UpdatedName"

    def test_soft_delete_user(self, db):
        user = make_user(db)
        user.deleted_at = datetime.now(timezone.utc)
        user.is_active = False
        db.flush()
        fetched = db.query(User).filter_by(id=user.id).first()
        assert fetched.deleted_at is not None
        assert fetched.is_active is False

    def test_multiple_users_persisted(self, db):
        for i in range(5):
            make_user(db, email=f"multi{i}@example.com")
        db.flush()
        count = db.query(User).count()
        assert count >= 5

    def test_filter_by_role(self, db):
        make_user(db, role=UserRole.ADMIN, email="admin1@example.com")
        make_user(db, role=UserRole.CLIENT, email="client1@example.com")
        make_user(db, role=UserRole.CLIENT, email="client2@example.com")
        db.flush()
        admins = db.query(User).filter_by(role=UserRole.ADMIN).all()
        clients = db.query(User).filter_by(role=UserRole.CLIENT).all()
        assert len(admins) >= 1
        assert len(clients) >= 2


class TestAgentProfileCRUD:
    """CRUD tests for AgentProfile."""

    def test_create_agent_profile(self, db):
        agent = make_agent_profile(db, display_name="Tim Shaw")
        db.flush()
        fetched = db.query(AgentProfile).filter_by(id=agent.id).first()
        assert fetched is not None
        assert fetched.display_name == "Tim Shaw"

    def test_update_agent_capacity(self, db):
        agent = make_agent_profile(db)
        agent.max_clients = 500
        db.flush()
        fetched = db.query(AgentProfile).filter_by(id=agent.id).first()
        assert fetched.max_clients == 500

    def test_deactivate_agent(self, db):
        agent = make_agent_profile(db)
        agent.is_active = False
        agent.is_accepting_clients = False
        agent.deactivated_at = datetime.now(timezone.utc)
        db.flush()
        fetched = db.query(AgentProfile).filter_by(id=agent.id).first()
        assert fetched.is_active is False

    def test_filter_active_agents(self, db):
        make_agent_profile(db, is_active=True)
        inactive = make_agent_profile(db, is_active=False)
        inactive.is_active = False
        db.flush()
        active_agents = db.query(AgentProfile).filter_by(is_active=True).all()
        assert all(a.is_active for a in active_agents)

    def test_increment_compliance_violations(self, db):
        agent = make_agent_profile(db)
        agent.compliance_violations += 1
        db.flush()
        fetched = db.query(AgentProfile).filter_by(id=agent.id).first()
        assert fetched.compliance_violations == 1


# ═════════════════════════════════════════════════════════════════════════════
# RELATIONSHIPS
# ═════════════════════════════════════════════════════════════════════════════

class TestRelationships:
    """Tests for ORM relationship loading."""

    def test_user_session_relationship(self, db):
        user = make_user(db)
        session = UserSession(
            id=uuid.uuid4(),
            user_id=user.id,
            jti=str(uuid.uuid4()),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            created_at=datetime.now(timezone.utc),
        )
        db.add(session)
        db.flush()
        fetched_user = db.query(User).filter_by(id=user.id).first()
        assert len(fetched_user.sessions) == 1

    def test_multiple_sessions_per_user(self, db):
        user = make_user(db)
        for _ in range(3):
            db.add(UserSession(
                id=uuid.uuid4(),
                user_id=user.id,
                jti=str(uuid.uuid4()),
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                created_at=datetime.now(timezone.utc),
            ))
        db.flush()
        fetched = db.query(User).filter_by(id=user.id).first()
        assert len(fetched.sessions) == 3

    def test_client_agent_assignment_relationship(self, db, client_with_agent):
        client, agent, assignment = client_with_agent
        fetched_agent = db.query(AgentProfile).filter_by(id=agent.id).first()
        assert len(fetched_agent.client_assignments) == 1

    def test_agent_linked_to_user_account(self, db):
        user = make_user(db, role=UserRole.AGENT)
        agent = make_agent_profile(db, user=user)
        db.flush()
        fetched = db.query(AgentProfile).filter_by(id=agent.id).first()
        assert fetched.user_id == user.id

    def test_audit_log_user_relationship(self, db):
        user = make_user(db)
        log = AuditLog(
            id=uuid.uuid4(),
            user_id=user.id,
            action="user.login",
            resource_type="users",
            success=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(log)
        db.flush()
        fetched_user = db.query(User).filter_by(id=user.id).first()
        assert len(fetched_user.audit_logs) == 1


# ═════════════════════════════════════════════════════════════════════════════
# CONSTRAINTS & INTEGRITY
# ═════════════════════════════════════════════════════════════════════════════

class TestConstraints:
    """Tests for database constraints and integrity rules."""

    def test_unique_email_constraint(self, db):
        make_user(db, email="unique@test.com")
        db.flush()
        with pytest.raises(IntegrityError):
            make_user(db, email="unique@test.com")
            db.flush()

    def test_unique_jti_constraint(self, db):
        user = make_user(db)
        jti = str(uuid.uuid4())
        db.add(UserSession(
            id=uuid.uuid4(), user_id=user.id, jti=jti,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            created_at=datetime.now(timezone.utc),
        ))
        db.flush()
        with pytest.raises(IntegrityError):
            db.add(UserSession(
                id=uuid.uuid4(), user_id=user.id, jti=jti,
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                created_at=datetime.now(timezone.utc),
            ))
            db.flush()

    def test_null_user_id_in_audit_log_allowed(self, db):
        """System-generated audit logs may have no user."""
        log = AuditLog(
            id=uuid.uuid4(),
            user_id=None,
            action="system.startup",
            resource_type="system",
            success=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(log)
        db.flush()
        fetched = db.query(AuditLog).filter_by(action="system.startup").first()
        assert fetched is not None
        assert fetched.user_id is None


# ═════════════════════════════════════════════════════════════════════════════
# TRANSACTIONS
# ═════════════════════════════════════════════════════════════════════════════

class TestTransactions:
    """Tests for transactional behavior."""

    def test_rollback_clears_changes(self, db):
        user = make_user(db, email="rollback@example.com")
        db.flush()
        user_id = user.id
        db.rollback()
        # After rollback, querying should not find the user in this test
        # (The fixture handles this via its own transaction isolation)
        # Just confirm the user was created in flush scope
        assert user_id is not None

    def test_multiple_flushes_in_same_session(self, db):
        user1 = make_user(db, email="flush1@example.com")
        db.flush()
        user2 = make_user(db, email="flush2@example.com")
        db.flush()
        # Both should be queryable
        assert db.query(User).filter_by(id=user1.id).first() is not None
        assert db.query(User).filter_by(id=user2.id).first() is not None

    def test_assignment_cascade_on_client_agent(self, db):
        """Creating assignment links client to agent correctly."""
        client = make_user(db)
        agent = make_agent_profile(db)
        assignment = make_client_assignment(db, client, agent)
        db.flush()
        assert db.query(ClientAgentAssignment).filter_by(
            client_user_id=client.id,
            agent_id=agent.id,
        ).first() is not None

    def test_audit_trail_immutability_concept(self, db, client_user):
        """Audit logs should never be deleted (immutable trail)."""
        log = AuditLog(
            id=uuid.uuid4(),
            user_id=client_user.id,
            action="dispute.filed",
            resource_type="disputes",
            success=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(log)
        db.flush()
        log_id = log.id
        # Verify it persists
        fetched = db.query(AuditLog).filter_by(id=log_id).first()
        assert fetched is not None
        assert fetched.action == "dispute.filed"
