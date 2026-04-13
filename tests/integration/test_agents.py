"""
The Life Shield — Integration Tests: Agent System
Tests for AgentProfile CRUD, client-agent assignment logic,
compliance safety flags, and capacity management.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from models.agent import AgentProfile, ClientAgentAssignment
from models.user import User
from config.security import UserRole
from tests.conftest import (
    make_agent_profile,
    make_client_assignment,
    make_user,
)


# ═════════════════════════════════════════════════════════════════════════════
# AGENT PROFILE MANAGEMENT
# ═════════════════════════════════════════════════════════════════════════════

class TestAgentProfileManagement:
    """Tests for creating, updating, and querying agent profiles."""

    def test_create_minimal_agent(self, db):
        agent = make_agent_profile(db)
        db.flush()
        assert db.query(AgentProfile).filter_by(id=agent.id).first() is not None

    def test_create_full_agent_persona(self, db):
        agent = make_agent_profile(
            db,
            agent_name="Timothy Shaw",
            display_name="Tim Shaw",
            role="client_success_agent",
        )
        agent.tone = "warm and professional"
        agent.communication_style = "empathetic, concise, action-oriented"
        agent.greeting_template = "Hello {first_name}, this is Tim. How can I help you today?"
        agent.closing_template = "Is there anything else I can assist you with?"
        agent.voice_provider = "elevenlabs"
        agent.voice_id = "voice-tim-shaw-001"
        agent.avatar_type = "tavus"
        agent.disclosure_text = "AI Client Agent for The Life Shield"
        db.flush()
        fetched = db.query(AgentProfile).filter_by(id=agent.id).first()
        assert fetched.display_name == "Tim Shaw"
        assert fetched.voice_provider == "elevenlabs"
        assert "AI Client Agent" in fetched.disclosure_text

    def test_update_agent_performance_rating(self, db):
        agent = make_agent_profile(db)
        agent.performance_rating = 4.8
        agent.satisfaction_score = 4.9
        db.flush()
        fetched = db.query(AgentProfile).filter_by(id=agent.id).first()
        assert fetched.performance_rating == 4.8
        assert fetched.satisfaction_score == 4.9

    def test_list_active_agents(self, db):
        make_agent_profile(db, is_active=True)
        make_agent_profile(db, is_active=True)
        inactive = make_agent_profile(db)
        inactive.is_active = False
        db.flush()
        active = db.query(AgentProfile).filter_by(is_active=True).all()
        assert all(a.is_active for a in active)

    def test_agent_specialties_json(self, db):
        agent = make_agent_profile(db)
        agent.specialties = {
            "skills": ["fcra_disputes", "budgeting", "credit_coaching"],
            "certifications": ["NFCC", "credit_counselor"]
        }
        db.flush()
        fetched = db.query(AgentProfile).filter_by(id=agent.id).first()
        assert "fcra_disputes" in fetched.specialties["skills"]

    def test_multiple_agent_roles(self, db):
        roles = [
            "client_success_agent",
            "credit_analyst",
            "compliance_agent",
            "scheduler",
            "recommendation_agent",
            "supervisor",
        ]
        for role in roles:
            make_agent_profile(db, role=role)
        db.flush()
        for role in roles:
            agent = db.query(AgentProfile).filter_by(role=role).first()
            assert agent is not None, f"Agent with role {role!r} not found"


# ═════════════════════════════════════════════════════════════════════════════
# COMPLIANCE SAFETY FLAGS (CRITICAL)
# ═════════════════════════════════════════════════════════════════════════════

class TestAgentComplianceSafety:
    """
    Critical compliance tests — these flags protect against regulatory violations.
    FCRA/CROA/FTC require these to ALWAYS be false.
    """

    def test_new_agent_cannot_make_promises(self, db):
        """CROA: Agents must NEVER make promises about credit score improvement."""
        agent = make_agent_profile(db)
        assert agent.can_make_promises is False, (
            "CRITICAL: can_make_promises must always be False (CROA compliance)"
        )

    def test_new_agent_cannot_override_decisions(self, db):
        """Human oversight: Only humans can override agent decisions."""
        agent = make_agent_profile(db)
        assert agent.can_override_decisions is False, (
            "CRITICAL: can_override_decisions must always be False (human oversight)"
        )

    def test_new_agent_cannot_file_disputes_by_default(self, db):
        """Disputes require human approval — agents cannot file without approval workflow."""
        agent = make_agent_profile(db)
        assert agent.can_file_disputes is False, (
            "Agents should not file disputes without human approval"
        )

    def test_new_agent_cannot_recommend_products_by_default(self, db):
        """Product recommendations require compliance check first."""
        agent = make_agent_profile(db)
        assert agent.can_recommend_products is False

    def test_agent_knows_compliance_regulations_by_default(self, db):
        """Agents must have knowledge flags set for all applicable regulations."""
        agent = make_agent_profile(db)
        assert agent.knows_fcra is True
        assert agent.knows_croa is True
        assert agent.knows_fcc_rules is True
        assert agent.knows_nc_regulations is True

    def test_agent_can_escalate_by_default(self, db):
        """Agents must always be able to escalate to humans."""
        agent = make_agent_profile(db)
        assert agent.can_escalate is True

    def test_ai_disclosure_text_present(self, db):
        """FTC: AI agents must have disclosure text configured."""
        agent = make_agent_profile(db)
        assert agent.disclosure_text
        assert len(agent.disclosure_text) > 0

    def test_compliance_violation_counter_tracked(self, db):
        """Compliance violations must be tracked for monitoring."""
        agent = make_agent_profile(db)
        original_count = agent.compliance_violations
        agent.compliance_violations += 1
        db.flush()
        fetched = db.query(AgentProfile).filter_by(id=agent.id).first()
        assert fetched.compliance_violations == original_count + 1


# ═════════════════════════════════════════════════════════════════════════════
# CLIENT-AGENT ASSIGNMENT
# ═════════════════════════════════════════════════════════════════════════════

class TestClientAgentAssignment:
    """Tests for assigning clients to agents and managing assignments."""

    def test_assign_client_to_agent(self, db):
        client = make_user(db, role=UserRole.CLIENT)
        agent = make_agent_profile(db)
        assignment = make_client_assignment(db, client, agent)
        db.flush()
        fetched = db.query(ClientAgentAssignment).filter_by(
            client_user_id=client.id,
            agent_id=agent.id,
        ).first()
        assert fetched is not None
        assert fetched.is_active is True

    def test_one_client_one_active_assignment(self, db):
        """Business rule: Client should only have one active agent."""
        client = make_user(db)
        agent1 = make_agent_profile(db)
        agent2 = make_agent_profile(db)
        # First assignment
        assignment1 = make_client_assignment(db, client, agent1)
        db.flush()
        # Deactivate first assignment (simulating reassignment)
        assignment1.is_active = False
        assignment1.reassigned_at = datetime.now(timezone.utc)
        # Second assignment
        make_client_assignment(db, client, agent2)
        db.flush()
        active = db.query(ClientAgentAssignment).filter_by(
            client_user_id=client.id,
            is_active=True,
        ).all()
        assert len(active) == 1

    def test_multiple_clients_per_agent(self, db):
        agent = make_agent_profile(db)
        clients = [make_user(db) for _ in range(5)]
        for client in clients:
            make_client_assignment(db, client, agent)
        db.flush()
        assignments = db.query(ClientAgentAssignment).filter_by(
            agent_id=agent.id,
            is_active=True,
        ).all()
        assert len(assignments) == 5

    def test_assignment_with_admin_assigner(self, db):
        """Track which admin assigned the client."""
        client = make_user(db)
        agent = make_agent_profile(db)
        admin = make_user(db, role=UserRole.ADMIN)
        assignment = make_client_assignment(
            db, client, agent,
            assigned_by_user_id=admin.id,
            notes="High-value client, VIP tier",
        )
        db.flush()
        fetched = db.query(ClientAgentAssignment).filter_by(id=assignment.id).first()
        assert fetched.assigned_by_user_id == admin.id
        assert "VIP tier" in fetched.notes

    def test_reassign_client_to_different_agent(self, db):
        client = make_user(db)
        agent1 = make_agent_profile(db, display_name="Agent One")
        agent2 = make_agent_profile(db, display_name="Agent Two")

        # Initial assignment
        old_assignment = make_client_assignment(db, client, agent1)
        db.flush()

        # Reassign
        old_assignment.is_active = False
        old_assignment.reassigned_at = datetime.now(timezone.utc)
        new_assignment = make_client_assignment(db, client, agent2)
        db.flush()

        assert not old_assignment.is_active
        assert new_assignment.is_active
        assert new_assignment.agent_id == agent2.id

    def test_get_active_agent_for_client(self, db):
        client = make_user(db)
        agent = make_agent_profile(db, display_name="Tim Shaw")
        make_client_assignment(db, client, agent)
        db.flush()

        active = db.query(ClientAgentAssignment).filter_by(
            client_user_id=client.id,
            is_active=True,
        ).first()
        assert active is not None
        fetched_agent = db.query(AgentProfile).filter_by(id=active.agent_id).first()
        assert fetched_agent.display_name == "Tim Shaw"


# ═════════════════════════════════════════════════════════════════════════════
# AGENT CAPACITY
# ═════════════════════════════════════════════════════════════════════════════

class TestAgentCapacity:
    """Tests for agent capacity tracking."""

    def test_agent_at_capacity_check(self, db):
        """Simulate checking if agent can accept more clients."""
        agent = make_agent_profile(db)
        agent.max_clients = 3
        agent.is_accepting_clients = True
        db.flush()

        # Create 3 clients
        for _ in range(3):
            client = make_user(db)
            make_client_assignment(db, client, agent)
        db.flush()

        # Count active assignments
        active_count = db.query(ClientAgentAssignment).filter_by(
            agent_id=agent.id,
            is_active=True,
        ).count()

        # At capacity — business logic would disable accepting
        if active_count >= agent.max_clients:
            agent.is_accepting_clients = False

        assert agent.is_accepting_clients is False

    def test_agent_below_capacity_accepting(self, db):
        agent = make_agent_profile(db)
        agent.max_clients = 10
        db.flush()

        client = make_user(db)
        make_client_assignment(db, client, agent)
        db.flush()

        active_count = db.query(ClientAgentAssignment).filter_by(
            agent_id=agent.id, is_active=True
        ).count()

        assert active_count < agent.max_clients
        assert agent.is_accepting_clients is True
