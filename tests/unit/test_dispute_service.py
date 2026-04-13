"""
Unit Tests — Dispute Service

Tests the dispute lifecycle service functions.
Uses SQLite in-memory database for isolation (no PostgreSQL required).
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.client import ClientProfile, BureauName as ModelBureauName, ClientStatus
from app.models.dispute import (
    DisputeCase,
    DisputeLetter,
    DisputeReason,
    DisputeStatus,
    LetterStatus,
)
from app.models.user import User, UserRole
from app.services.dispute_service import (
    _compliance_check,
    approve_dispute_letter,
    create_dispute_case,
    generate_dispute_letter,
    get_disputes_for_client,
    reject_dispute_letter,
)


# ─────────────────────────────────────────────────────────
# Test Database Setup
# ─────────────────────────────────────────────────────────

@pytest.fixture
def db(shared_engine):
    """Provide a transactional database session, rolled back after each test."""
    connection = shared_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def test_user(db):
    user = User(
        id=uuid.uuid4(),
        email=f"test-{uuid.uuid4()}@example.com",
        password_hash="$2b$12$test",
        role=UserRole.ADMIN,
        email_verified=True,
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def test_client(db, test_user):
    profile = ClientProfile(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="John Doe",
        address_line1="123 Main St",
        city="Charlotte",
        state="NC",
        zip_code="28201",
        subscription_status=ClientStatus.ACTIVE,
        ssn_last_4="5000",
    )
    db.add(profile)
    db.flush()
    return profile


# ─────────────────────────────────────────────────────────
# Compliance Check Tests
# ─────────────────────────────────────────────────────────

class TestComplianceCheck:

    def test_clean_letter_passes(self):
        letter = (
            "I am writing to dispute an inaccurate item on my credit report. "
            "The account listed under Midland Credit Management does not belong to me. "
            "I request investigation per the Fair Credit Reporting Act."
        )
        status, flags = _compliance_check(letter)
        assert status == "passed"
        assert len(flags) == 0

    def test_guaranteed_removal_flagged(self):
        letter = (
            "We guaranteed removal of all negative items from your credit report. "
            "100% removal guaranteed within 30 days."
        )
        status, flags = _compliance_check(letter)
        assert status == "flagged"
        assert len(flags) >= 2

    def test_new_credit_identity_flagged(self):
        letter = "We can create a new credit identity for you using a CPN number."
        status, flags = _compliance_check(letter)
        assert status == "flagged"
        # Should catch 'new credit identity' and 'cpn'
        assert len(flags) >= 1

    def test_too_short_flagged(self):
        letter = "Dispute this."
        status, flags = _compliance_check(letter)
        assert status == "flagged"
        assert any("too short" in f.lower() for f in flags)

    def test_missing_dispute_basis_flagged(self):
        letter = "A" * 200  # Long enough but no dispute keywords
        status, flags = _compliance_check(letter)
        assert status == "flagged"

    def test_fcra_reference_passes(self):
        letter = (
            "I dispute the following inaccurate information on my credit report. "
            "Per the FCRA, I request a full reinvestigation of this item. "
            "The account is incorrect and not authorized by me."
        )
        status, flags = _compliance_check(letter)
        assert status == "passed"

    def test_erase_keyword_flagged(self):
        letter = (
            "We will erase all bad credit from your report. "
            "This item is inaccurate and disputed."
        )
        status, flags = _compliance_check(letter)
        assert status == "flagged"


# ─────────────────────────────────────────────────────────
# Create Dispute Case Tests
# ─────────────────────────────────────────────────────────

class TestCreateDisputeCase:

    def test_create_basic_dispute(self, db, test_client, test_user):
        case = create_dispute_case(
            db=db,
            client=test_client,
            bureau="equifax",
            dispute_reason="not_mine",
            creditor_name="Midland Credit Management",
            account_number_masked="****4521",
            actor_user_id=test_user.id,
        )

        assert case is not None
        assert case.id is not None
        assert case.client_id == test_client.id
        assert case.bureau == "equifax"
        assert case.dispute_reason == DisputeReason.NOT_MINE
        assert case.creditor_name == "Midland Credit Management"
        assert case.status == DisputeStatus.PENDING_APPROVAL  # Always starts here
        assert case.priority_score == 5

    def test_create_dispute_all_bureaus(self, db, test_client):
        for bureau in ["equifax", "experian", "transunion"]:
            case = create_dispute_case(
                db=db,
                client=test_client,
                bureau=bureau,
                dispute_reason="inaccurate",
                creditor_name="Test Creditor",
            )
            assert case.bureau == bureau

    def test_create_dispute_all_reasons(self, db, test_client):
        reasons = [
            "inaccurate", "incomplete", "unverifiable", "obsolete",
            "fraudulent", "not_mine", "wrong_balance", "wrong_status", "duplicate",
        ]
        for reason in reasons:
            case = create_dispute_case(
                db=db,
                client=test_client,
                bureau="equifax",
                dispute_reason=reason,
                creditor_name="Test",
            )
            assert case.dispute_reason.value == reason

    def test_create_dispute_invalid_reason_raises(self, db, test_client):
        with pytest.raises(ValueError, match="Invalid dispute reason"):
            create_dispute_case(
                db=db,
                client=test_client,
                bureau="equifax",
                dispute_reason="not_valid_reason",
                creditor_name="Test",
            )

    def test_dispute_always_starts_pending_approval(self, db, test_client):
        """CRITICAL: No dispute should ever start as FILED or APPROVED."""
        case = create_dispute_case(
            db=db,
            client=test_client,
            bureau="equifax",
            dispute_reason="inaccurate",
            creditor_name="Test",
        )
        assert case.status == DisputeStatus.PENDING_APPROVAL

    def test_audit_entry_created(self, db, test_client, test_user):
        from app.models.audit import AuditTrail, AuditAction

        initial_count = db.query(AuditTrail).count()

        create_dispute_case(
            db=db,
            client=test_client,
            bureau="equifax",
            dispute_reason="inaccurate",
            creditor_name="Test Creditor",
            actor_user_id=test_user.id,
        )

        final_count = db.query(AuditTrail).count()
        assert final_count == initial_count + 1

        latest = db.query(AuditTrail).order_by(AuditTrail.created_at.desc()).first()
        assert latest.action == AuditAction.DISPUTE_CREATED
        assert latest.client_id == test_client.id


# ─────────────────────────────────────────────────────────
# Generate Letter Tests
# ─────────────────────────────────────────────────────────

class TestGenerateDisputeLetter:

    @pytest.fixture
    def dispute(self, db, test_client):
        case = create_dispute_case(
            db=db,
            client=test_client,
            bureau="equifax",
            dispute_reason="not_mine",
            creditor_name="Midland Credit Management",
            account_number_masked="****4521",
        )
        return case

    def test_generate_letter_creates_record(self, db, test_client, dispute):
        letter = generate_dispute_letter(
            db=db,
            dispute_case=dispute,
            client=test_client,
        )

        assert letter is not None
        assert letter.id is not None
        assert letter.dispute_id == dispute.id
        assert letter.client_id == test_client.id
        assert letter.letter_content is not None
        assert len(letter.letter_content) > 100
        assert letter.letter_version == 1
        assert letter.human_approval_required is True  # ALWAYS required

    def test_letter_always_requires_human_approval(self, db, test_client, dispute):
        """CRITICAL: human_approval_required must always be True."""
        letter = generate_dispute_letter(
            db=db,
            dispute_case=dispute,
            client=test_client,
        )
        assert letter.human_approval_required is True

    def test_letter_contains_creditor_name(self, db, test_client, dispute):
        letter = generate_dispute_letter(
            db=db,
            dispute_case=dispute,
            client=test_client,
        )
        assert "Midland Credit Management" in letter.letter_content

    def test_letter_contains_fcra_reference(self, db, test_client, dispute):
        letter = generate_dispute_letter(
            db=db,
            dispute_case=dispute,
            client=test_client,
        )
        content_lower = letter.letter_content.lower()
        assert "fcra" in content_lower or "fair credit reporting" in content_lower

    def test_letter_compliance_checked(self, db, test_client, dispute):
        letter = generate_dispute_letter(
            db=db,
            dispute_case=dispute,
            client=test_client,
        )
        assert letter.compliance_status in ("passed", "flagged")
        assert letter.compliance_checked_at is not None

    def test_letter_version_increments(self, db, test_client, dispute):
        letter1 = generate_dispute_letter(db=db, dispute_case=dispute, client=test_client)
        assert letter1.letter_version == 1

        # Generate second version
        letter2 = generate_dispute_letter(db=db, dispute_case=dispute, client=test_client)
        assert letter2.letter_version == 2

    def test_letter_has_ai_model_tracked(self, db, test_client, dispute):
        letter = generate_dispute_letter(db=db, dispute_case=dispute, client=test_client)
        assert letter.ai_model_used is not None
        assert len(letter.ai_model_used) > 0


# ─────────────────────────────────────────────────────────
# Approval / Rejection Tests
# ─────────────────────────────────────────────────────────

class TestLetterApproval:

    @pytest.fixture
    def approved_letter_setup(self, db, test_client, test_user):
        dispute = create_dispute_case(
            db=db,
            client=test_client,
            bureau="equifax",
            dispute_reason="inaccurate",
            creditor_name="Test Creditor",
        )
        letter = generate_dispute_letter(db=db, dispute_case=dispute, client=test_client)

        # Force compliance to passed for approval testing
        letter.compliance_status = "passed"
        db.flush()

        return dispute, letter

    def test_approve_letter_transitions_status(self, db, test_user, approved_letter_setup):
        dispute, letter = approved_letter_setup

        approved = approve_dispute_letter(
            db=db,
            letter=letter,
            dispute_case=dispute,
            approving_admin_id=test_user.id,
        )

        assert approved.status == LetterStatus.APPROVED
        assert approved.approved_by_admin_id == test_user.id
        assert approved.approval_date is not None

    def test_approve_letter_updates_dispute_status(self, db, test_user, approved_letter_setup):
        dispute, letter = approved_letter_setup

        approve_dispute_letter(
            db=db,
            letter=letter,
            dispute_case=dispute,
            approving_admin_id=test_user.id,
        )

        assert dispute.status == DisputeStatus.APPROVED

    def test_cannot_approve_flagged_letter(self, db, test_client, test_user):
        dispute = create_dispute_case(
            db=db,
            client=test_client,
            bureau="equifax",
            dispute_reason="inaccurate",
            creditor_name="Test",
        )
        letter = generate_dispute_letter(db=db, dispute_case=dispute, client=test_client)
        letter.compliance_status = "flagged"
        letter.compliance_flags = ["Forbidden phrase: 'guaranteed'"]
        db.flush()

        with pytest.raises(ValueError, match="compliance"):
            approve_dispute_letter(
                db=db,
                letter=letter,
                dispute_case=dispute,
                approving_admin_id=test_user.id,
            )

    def test_reject_letter_sets_revision_status(self, db, test_user, approved_letter_setup):
        dispute, letter = approved_letter_setup

        rejected = reject_dispute_letter(
            db=db,
            letter=letter,
            dispute_case=dispute,
            rejecting_admin_id=test_user.id,
            reason="Letter content needs revision — remove the guarantee language",
        )

        assert rejected.status == LetterStatus.REVISION_REQUESTED
        assert rejected.rejection_reason is not None
        assert "guarantee" in rejected.rejection_reason.lower()


# ─────────────────────────────────────────────────────────
# Query Tests
# ─────────────────────────────────────────────────────────

class TestGetDisputes:

    def test_get_disputes_for_client(self, db, test_client):
        # Create multiple disputes
        for i in range(3):
            create_dispute_case(
                db=db,
                client=test_client,
                bureau="equifax",
                dispute_reason="inaccurate",
                creditor_name=f"Creditor {i}",
            )

        disputes = get_disputes_for_client(db, test_client.id)
        assert len(disputes) >= 3

    def test_filter_by_bureau(self, db, test_client):
        create_dispute_case(db=db, client=test_client, bureau="experian", dispute_reason="inaccurate", creditor_name="EXP Test")

        experian_disputes = get_disputes_for_client(db, test_client.id, bureau_filter="experian")
        for d in experian_disputes:
            assert d.bureau == "experian"

    def test_pagination(self, db, test_client):
        # Create 5 disputes
        for i in range(5):
            create_dispute_case(
                db=db, client=test_client, bureau="equifax",
                dispute_reason="inaccurate", creditor_name=f"Creditor {i}",
            )

        page1 = get_disputes_for_client(db, test_client.id, limit=2, offset=0)
        page2 = get_disputes_for_client(db, test_client.id, limit=2, offset=2)

        assert len(page1) == 2
        assert len(page2) == 2
        assert {d.id for d in page1}.isdisjoint({d.id for d in page2})
