"""
Unit Tests — Credit Report Service

Tests credit report pulling, storage, and snapshot creation.
Uses SQLite in-memory database.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.client import ClientProfile, CreditReport, CreditReportSnapshot, Tradeline, ClientStatus
from app.models.user import User, UserRole
from app.services.credit_report_service import (
    _parse_date,
    get_latest_reports,
    pull_credit_report,
    pull_soft_pull_tri_merge,
)


# ─────────────────────────────────────────────────────────
# Database Fixtures
# ─────────────────────────────────────────────────────────

@pytest.fixture
def db(shared_engine):
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
        full_name="Alice Johnson",
        address_line1="100 Main St",
        city="Charlotte",
        state="NC",
        zip_code="28201",
        date_of_birth=datetime(1985, 6, 15, tzinfo=timezone.utc),
        subscription_status=ClientStatus.ACTIVE,
        ssn_last_4="0000",  # Excellent credit scenario
    )
    db.add(profile)
    db.flush()
    return profile


@pytest.fixture
def poor_credit_client(db, test_user):
    """Client with poor credit (SSN last4 = 9999)."""
    profile = ClientProfile(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Bob Smith",
        address_line1="200 Oak Ave",
        city="Raleigh",
        state="NC",
        zip_code="27601",
        subscription_status=ClientStatus.ACTIVE,
        ssn_last_4="9999",  # Poor credit scenario
    )
    db.add(profile)
    db.flush()
    return profile


# ─────────────────────────────────────────────────────────
# Parse Date Tests
# ─────────────────────────────────────────────────────────

class TestParseDateHelper:

    def test_iso_format(self):
        result = _parse_date("2025-03-15")
        assert result is not None
        assert result.year == 2025
        assert result.month == 3
        assert result.day == 15

    def test_us_format(self):
        result = _parse_date("03/15/2025")
        assert result is not None
        assert result.year == 2025

    def test_iso_datetime(self):
        result = _parse_date("2025-03-15T10:30:00Z")
        assert result is not None
        assert result.year == 2025

    def test_none_input(self):
        assert _parse_date(None) is None

    def test_empty_string(self):
        assert _parse_date("") is None

    def test_invalid_date(self):
        assert _parse_date("not-a-date") is None


# ─────────────────────────────────────────────────────────
# Pull Credit Report Tests (Sandbox)
# ─────────────────────────────────────────────────────────

class TestPullCreditReport:

    def test_pull_single_bureau_equifax(self, db, test_client):
        reports = pull_credit_report(
            db=db,
            client=test_client,
            decrypted_ssn="000-00-0000",
            bureaus=["equifax"],
            pull_type="full",
        )

        assert "equifax" in reports
        report = reports["equifax"]
        assert isinstance(report, CreditReport)
        assert report.client_id == test_client.id
        assert report.bureau.value == "equifax"
        assert report.score is not None
        assert report.score >= 750  # Excellent credit (SSN 0000)
        assert report.tradelines_count > 0

    def test_pull_all_three_bureaus(self, db, test_client):
        reports = pull_credit_report(
            db=db,
            client=test_client,
            decrypted_ssn="000-00-0000",
            bureaus=["equifax", "experian", "transunion"],
            pull_type="full",
        )

        assert len(reports) == 3
        assert "equifax" in reports
        assert "experian" in reports
        assert "transunion" in reports

    def test_reports_stored_in_database(self, db, test_client):
        initial_count = db.query(CreditReport).filter(CreditReport.client_id == test_client.id).count()

        pull_credit_report(
            db=db,
            client=test_client,
            decrypted_ssn="000-00-0000",
            bureaus=["equifax"],
            pull_type="full",
        )

        final_count = db.query(CreditReport).filter(CreditReport.client_id == test_client.id).count()
        assert final_count == initial_count + 1

    def test_tradelines_stored_in_database(self, db, poor_credit_client):
        pull_credit_report(
            db=db,
            client=poor_credit_client,
            decrypted_ssn="000-00-9999",
            bureaus=["equifax"],
            pull_type="full",
        )

        tradelines = db.query(Tradeline).filter(Tradeline.client_id == poor_credit_client.id).all()
        assert len(tradelines) > 0

    def test_client_scores_updated(self, db, test_client):
        assert test_client.current_score_equifax is None

        pull_credit_report(
            db=db,
            client=test_client,
            decrypted_ssn="000-00-0000",
            bureaus=["equifax"],
            pull_type="full",
        )

        assert test_client.current_score_equifax is not None
        assert test_client.score_updated_at is not None

    def test_all_bureaus_update_client_scores(self, db, test_client):
        pull_credit_report(
            db=db,
            client=test_client,
            decrypted_ssn="000-00-0000",
            bureaus=["equifax", "experian", "transunion"],
            pull_type="full",
        )

        assert test_client.current_score_equifax is not None
        assert test_client.current_score_experian is not None
        assert test_client.current_score_transunion is not None

    def test_snapshot_created(self, db, test_client):
        initial_snapshots = db.query(CreditReportSnapshot).filter(
            CreditReportSnapshot.client_id == test_client.id
        ).count()

        pull_credit_report(
            db=db,
            client=test_client,
            decrypted_ssn="000-00-0000",
            bureaus=["equifax"],
        )

        final_snapshots = db.query(CreditReportSnapshot).filter(
            CreditReportSnapshot.client_id == test_client.id
        ).count()
        assert final_snapshots == initial_snapshots + 1

    def test_audit_entries_created(self, db, test_client):
        from app.models.audit import AuditTrail, AuditAction

        initial_count = db.query(AuditTrail).filter(AuditTrail.client_id == test_client.id).count()

        pull_credit_report(
            db=db,
            client=test_client,
            decrypted_ssn="000-00-0000",
            bureaus=["equifax"],
        )

        final_count = db.query(AuditTrail).filter(AuditTrail.client_id == test_client.id).count()
        assert final_count > initial_count  # At least pull_requested + stored entries

    def test_soft_pull_type_stored(self, db, test_client):
        pull_credit_report(
            db=db,
            client=test_client,
            decrypted_ssn="000-00-0000",
            bureaus=["equifax"],
            pull_type="soft",
        )

        report = (
            db.query(CreditReport)
            .filter(CreditReport.client_id == test_client.id)
            .order_by(CreditReport.pull_date.desc())
            .first()
        )
        assert report.pull_type == "soft"

    def test_poor_credit_has_negative_items(self, db, poor_credit_client):
        reports = pull_credit_report(
            db=db,
            client=poor_credit_client,
            decrypted_ssn="000-00-9999",
            bureaus=["equifax"],
            pull_type="full",
        )

        report = reports["equifax"]
        assert report.negative_items_count >= 2
        assert report.collections_count >= 1

    def test_empty_bureaus_list_returns_empty(self, db, test_client):
        reports = pull_credit_report(
            db=db,
            client=test_client,
            decrypted_ssn="000-00-0000",
            bureaus=[],
        )
        assert reports == {}


# ─────────────────────────────────────────────────────────
# Soft Pull (iSoftPull) Tests
# ─────────────────────────────────────────────────────────

class TestSoftPullTriMerge:

    def test_tri_merge_returns_three_bureaus(self, db, test_client):
        reports = pull_soft_pull_tri_merge(
            db=db,
            client=test_client,
            decrypted_ssn="000-00-0000",
        )

        assert len(reports) == 3
        assert "equifax" in reports
        assert "experian" in reports
        assert "transunion" in reports

    def test_tri_merge_reports_stored_as_soft(self, db, test_client):
        pull_soft_pull_tri_merge(
            db=db,
            client=test_client,
            decrypted_ssn="000-00-0000",
        )

        soft_reports = (
            db.query(CreditReport)
            .filter(
                CreditReport.client_id == test_client.id,
                CreditReport.pull_type == "soft",
            )
            .all()
        )
        assert len(soft_reports) >= 3


# ─────────────────────────────────────────────────────────
# Get Latest Reports Tests
# ─────────────────────────────────────────────────────────

class TestGetLatestReports:

    def test_returns_latest_per_bureau(self, db, test_client):
        # Pull twice — should get the latest each time
        pull_credit_report(db=db, client=test_client, decrypted_ssn="000-00-0000", bureaus=["equifax"])
        pull_credit_report(db=db, client=test_client, decrypted_ssn="000-00-0000", bureaus=["equifax"])

        latest = get_latest_reports(db, test_client.id)

        equifax_reports = [r for r in latest if r.bureau.value == "equifax"]
        assert len(equifax_reports) == 1  # Only most recent

    def test_no_reports_returns_empty_list(self, db, test_user):
        """Client with no reports returns empty list."""
        fresh_client = ClientProfile(
            id=uuid.uuid4(),
            user_id=test_user.id,
            full_name="Fresh Client",
            address_line1="999 New St",
            city="Test City",
            state="NC",
            zip_code="28000",
            subscription_status=ClientStatus.ACTIVE,
        )
        db.add(fresh_client)
        db.flush()

        latest = get_latest_reports(db, fresh_client.id)
        assert latest == []
