"""
The Life Shield — Unit Tests: Database Models
Tests for User, UserSession, AuditLog, AgentProfile, ClientAgentAssignment.
Validates field constraints, relationships, properties, and repr strings.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from models.user import AuditLog, User, UserSession
from models.agent import AgentProfile, ClientAgentAssignment
from config.security import UserRole

from tests.conftest import make_agent_profile, make_user, make_client_assignment


# ═════════════════════════════════════════════════════════════════════════════
# USER MODEL
# ═════════════════════════════════════════════════════════════════════════════

class TestUserModel:
    """Tests for User ORM model."""

    def test_user_created_and_persisted(self, db):
        user = make_user(db)
        db.commit()
        fetched = db.query(User).filter_by(id=user.id).first()
        assert fetched is not None
        assert fetched.email == user.email

    def test_email_is_unique(self, db):
        from sqlalchemy.exc import IntegrityError
        email = "unique@example.com"
        make_user(db, email=email)
        db.flush()
        with pytest.raises(IntegrityError):
            make_user(db, email=email)
            db.flush()

    def test_full_name_property(self, db):
        user = make_user(db)
        user.first_name = "Sainte"
        user.last_name = "Robinson"
        assert user.full_name == "Sainte Robinson"

    def test_is_locked_false_when_no_lockout(self, db):
        user = make_user(db)
        user.locked_until = None
        assert user.is_locked is False

    def test_is_locked_false_when_past_lockout(self, db):
        user = make_user(db)
        user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        assert user.is_locked is False

    def test_is_locked_true_when_future_lockout(self, db):
        user = make_user(db)
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        assert user.is_locked is True

    def test_default_role_is_client(self, db):
        user = make_user(db, role=UserRole.CLIENT)
        assert user.role == UserRole.CLIENT

    def test_admin_role(self, db):
        user = make_user(db, role=UserRole.ADMIN)
        assert user.role == UserRole.ADMIN

    def test_default_is_active(self, db):
        user = make_user(db)
        assert user.is_active is True

    def test_default_sms_consent_false(self, db):
        user = make_user(db)
        assert user.sms_consent is False

    def test_consent_fields_settable(self, db):
        user = make_user(db)
        user.sms_consent = True
        user.sms_consent_at = datetime.now(timezone.utc)
        user.email_consent = True
        user.voice_consent = True
        assert user.sms_consent is True
        assert user.email_consent is True

    def test_repr_contains_email_and_role(self, db):
        user = make_user(db, email="repr@example.com", role=UserRole.ADMIN)
        r = repr(user)
        assert "repr@example.com" in r
        assert "admin" in r

    def test_deleted_at_defaults_none(self, db):
        user = make_user(db)
        assert user.deleted_at is None

    def test_soft_delete_sets_deleted_at(self, db):
        user = make_user(db)
        user.deleted_at = datetime.now(timezone.utc)
        assert user.deleted_at is not None


class TestUserRoles:
    """Tests for UserRole enum values."""

    def test_all_roles_defined(self):
        assert UserRole.ADMIN == "admin"
        assert UserRole.CLIENT == "client"
        assert UserRole.AGENT == "agent"

    def test_role_is_string_enum(self):
        assert isinstance(UserRole.ADMIN, str)


# ═════════════════════════════════════════════════════════════════════════════
# USER SESSION MODEL
# ═════════════════════════════════════════════════════════════════════════════

class TestUserSessionModel:
    """Tests for UserSession ORM model."""

    def _make_session(self, db, user: User, **kwargs) -> UserSession:
        session = UserSession(
            id=uuid.uuid4(),
            user_id=user.id,
            jti=str(uuid.uuid4()),
            device_type="web",
            ip_address="127.0.0.1",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            created_at=datetime.now(timezone.utc),
            **kwargs,
        )
        db.add(session)
        db.flush()
        return session

    def test_session_created(self, db, client_user):
        session = self._make_session(db, client_user)
        assert session.id is not None

    def test_is_valid_true_for_active_session(self, db, client_user):
        session = self._make_session(db, client_user)
        assert session.is_valid is True

    def test_is_valid_false_when_revoked(self, db, client_user):
        session = self._make_session(db, client_user)
        session.revoked_at = datetime.now(timezone.utc)
        assert session.is_valid is False

    def test_is_valid_false_when_expired(self, db, client_user):
        session = self._make_session(
            db, client_user,
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
        )
        assert session.is_valid is False

    def test_repr_contains_user_id(self, db, client_user):
        session = self._make_session(db, client_user)
        r = repr(session)
        assert str(client_user.id) in r

    def test_jti_is_unique(self, db, client_user):
        from sqlalchemy.exc import IntegrityError
        jti = str(uuid.uuid4())
        self._make_session(db, client_user, jti=jti)
        with pytest.raises(IntegrityError):
            self._make_session(db, client_user, jti=jti)

    def test_user_relationship_accessible(self, db, client_user):
        session = self._make_session(db, client_user)
        assert session.user_id == client_user.id


# ═════════════════════════════════════════════════════════════════════════════
# AUDIT LOG MODEL
# ═════════════════════════════════════════════════════════════════════════════

class TestAuditLogModel:
    """Tests for AuditLog ORM model."""

    def _make_audit(self, db, user: User | None = None, **kwargs) -> AuditLog:
        log = AuditLog(
            id=uuid.uuid4(),
            user_id=user.id if user else None,
            action=kwargs.pop("action", "user.login"),
            resource_type=kwargs.pop("resource_type", "users"),
            resource_id=str(uuid.uuid4()),
            success=True,
            created_at=datetime.now(timezone.utc),
            **kwargs,
        )
        db.add(log)
        db.flush()
        return log

    def test_audit_log_created(self, db, client_user):
        log = self._make_audit(db, client_user)
        assert log.id is not None

    def test_audit_log_without_user(self, db):
        """System actions have no user_id."""
        log = self._make_audit(db, user=None, action="system.startup")
        assert log.user_id is None

    def test_repr_contains_action(self, db, client_user):
        log = self._make_audit(db, client_user, action="user.password_changed")
        r = repr(log)
        assert "user.password_changed" in r

    def test_success_defaults_true(self, db, client_user):
        log = self._make_audit(db, client_user)
        assert log.success is True

    def test_failed_action_stored(self, db, client_user):
        log = self._make_audit(
            db, client_user,
            action="user.login",
            success=False,
            error_message="Invalid credentials",
        )
        assert log.success is False
        assert log.error_message == "Invalid credentials"

    def test_details_json_stored_as_text(self, db, client_user):
        import json
        details = json.dumps({"ip": "10.0.0.1", "attempt": 3})
        log = self._make_audit(db, client_user, details=details)
        assert "10.0.0.1" in log.details


# ═════════════════════════════════════════════════════════════════════════════
# AGENT PROFILE MODEL
# ═════════════════════════════════════════════════════════════════════════════

class TestAgentProfileModel:
    """Tests for AgentProfile ORM model."""

    def test_agent_created(self, db, agent_profile):
        assert agent_profile.id is not None

    def test_default_role(self, db):
        agent = make_agent_profile(db)
        assert agent.role == "client_success_agent"

    def test_display_name(self, db):
        agent = make_agent_profile(db, display_name="Tim Shaw")
        assert agent.display_name == "Tim Shaw"

    def test_compliance_flags_default_true(self, db):
        agent = make_agent_profile(db)
        assert agent.knows_fcra is True
        assert agent.knows_croa is True
        assert agent.knows_fcc_rules is True
        assert agent.knows_nc_regulations is True

    def test_can_make_promises_always_false(self, db):
        """Safety critical: agents must never be allowed to make promises."""
        agent = make_agent_profile(db)
        assert agent.can_make_promises is False

    def test_can_override_decisions_always_false(self, db):
        """Safety critical: only humans override decisions."""
        agent = make_agent_profile(db)
        assert agent.can_override_decisions is False

    def test_is_active_default_true(self, db):
        agent = make_agent_profile(db)
        assert agent.is_active is True

    def test_is_accepting_clients_default_true(self, db):
        agent = make_agent_profile(db)
        assert agent.is_accepting_clients is True

    def test_max_clients_default(self, db):
        agent = make_agent_profile(db)
        assert agent.max_clients == 2000

    def test_compliance_violations_default_zero(self, db):
        agent = make_agent_profile(db)
        assert agent.compliance_violations == 0

    def test_repr_contains_display_name(self, db):
        agent = make_agent_profile(db, display_name="Tim Shaw")
        r = repr(agent)
        assert "Tim Shaw" in r

    def test_assigned_client_count_no_assignments(self, db):
        agent = make_agent_profile(db)
        # No assignments loaded yet
        assert agent.assigned_client_count == 0

    def test_can_escalate_default_true(self, db):
        agent = make_agent_profile(db)
        assert agent.can_escalate is True

    def test_deactivate_agent(self, db):
        agent = make_agent_profile(db)
        agent.is_active = False
        agent.deactivated_at = datetime.now(timezone.utc)
        assert agent.is_active is False
        assert agent.deactivated_at is not None

    def test_specialties_json_field(self, db):
        specialties = {"skills": ["credit_repair", "fcra_disputes", "budgeting"]}
        agent = make_agent_profile(db)
        agent.specialties = specialties
        db.flush()
        assert agent.specialties["skills"] == ["credit_repair", "fcra_disputes", "budgeting"]


# ═════════════════════════════════════════════════════════════════════════════
# CLIENT-AGENT ASSIGNMENT MODEL
# ═════════════════════════════════════════════════════════════════════════════

class TestClientAgentAssignmentModel:
    """Tests for ClientAgentAssignment ORM model."""

    def test_assignment_created(self, db, client_with_agent):
        client, agent, assignment = client_with_agent
        assert assignment.id is not None
        assert assignment.client_user_id == client.id
        assert assignment.agent_id == agent.id

    def test_is_active_default_true(self, db):
        client = make_user(db)
        agent = make_agent_profile(db)
        assignment = make_client_assignment(db, client, agent)
        assert assignment.is_active is True

    def test_deactivate_assignment(self, db):
        client = make_user(db)
        agent = make_agent_profile(db)
        assignment = make_client_assignment(db, client, agent)
        assignment.is_active = False
        assignment.reassigned_at = datetime.now(timezone.utc)
        assert assignment.is_active is False

    def test_repr_contains_ids(self, db, client_with_agent):
        client, agent, assignment = client_with_agent
        r = repr(assignment)
        assert str(client.id) in r
        assert str(agent.id) in r

    def test_notes_field(self, db):
        client = make_user(db)
        agent = make_agent_profile(db)
        assignment = make_client_assignment(
            db, client, agent,
            notes="High-priority client, escalate quickly"
        )
        assert "High-priority client" in assignment.notes
