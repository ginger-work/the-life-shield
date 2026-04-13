"""
Unit Tests — Credit Bureau Integration Clients

Tests all four bureau clients in sandbox mode.
No external API calls are made — 100% sandbox.

Coverage targets:
- BaseBureauClient: report pull, dispute filing, status check
- EquifaxClient: pull, file, status
- ExperianClient: pull, file, status
- TransUnionClient: pull, file, status
- ISoftPullClient: tri-merge, monitoring
- Sandbox scenarios: excellent/fair/poor credit
- Error handling: timeouts, auth failures, retry logic
"""
import pytest
from datetime import datetime, timezone

from app.integrations.bureaus import (
    BureauAPIError,
    BureauAuthError,
    BureauName,
    ConsumerIdentity,
    DisputeFilingRequest,
    DisputeStatus,
    EquifaxClient,
    ExperianClient,
    ISoftPullClient,
    PullType,
    TransUnionClient,
)


# ─────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────

@pytest.fixture
def consumer_excellent():
    """Consumer with excellent credit (SSN ends in 0000)."""
    return ConsumerIdentity(
        first_name="Alice",
        last_name="Johnson",
        ssn="000-00-0000",
        date_of_birth="1985-06-15",
        address_line1="100 Main St",
        city="Charlotte",
        state="NC",
        zip_code="28201",
    )


@pytest.fixture
def consumer_fair():
    """Consumer with fair credit (SSN ends in 5000)."""
    return ConsumerIdentity(
        first_name="Bob",
        last_name="Smith",
        ssn="000-00-5000",
        date_of_birth="1978-11-22",
        address_line1="200 Oak Ave",
        city="Raleigh",
        state="NC",
        zip_code="27601",
    )


@pytest.fixture
def consumer_poor():
    """Consumer with poor credit (SSN ends in 9999)."""
    return ConsumerIdentity(
        first_name="Carol",
        last_name="Davis",
        ssn="000-00-9999",
        date_of_birth="1990-03-08",
        address_line1="300 Pine Rd",
        city="Durham",
        state="NC",
        zip_code="27701",
    )


@pytest.fixture
def dispute_request(consumer_excellent):
    return DisputeFilingRequest(
        consumer=consumer_excellent,
        tradeline_id_at_bureau="TL-12345",
        creditor_name="Midland Credit Management",
        account_number_masked="****4521",
        dispute_reason_code="not_mine",
        dispute_explanation=(
            "I have no knowledge of this account and never authorized it. "
            "This account does not belong to me. "
            "I request a full investigation per FCRA § 611."
        ),
    )


# ─────────────────────────────────────────────────────────
# Equifax Client Tests
# ─────────────────────────────────────────────────────────

class TestEquifaxClient:

    def test_sandbox_pull_excellent_credit(self, consumer_excellent):
        with EquifaxClient(sandbox=True) as client:
            result = client.pull_report(consumer_excellent, PullType.FULL)

        assert result.success is True
        assert result.bureau == BureauName.EQUIFAX
        assert result.pull_type == PullType.FULL
        assert result.credit_score >= 750
        assert result.reference_number.startswith("SANDBOX-EQU-")
        assert result.tradelines_count >= 1
        assert result.negative_items_count == 0
        assert result.pull_timestamp is not None
        assert result.parsed_data is not None
        assert "tradelines" in result.parsed_data
        assert "inquiries" in result.parsed_data

    def test_sandbox_pull_fair_credit(self, consumer_fair):
        with EquifaxClient(sandbox=True) as client:
            result = client.pull_report(consumer_fair, PullType.FULL)

        assert result.success is True
        assert 580 <= result.credit_score <= 699
        assert result.negative_items_count >= 1  # Late payment

    def test_sandbox_pull_poor_credit(self, consumer_poor):
        with EquifaxClient(sandbox=True) as client:
            result = client.pull_report(consumer_poor, PullType.FULL)

        assert result.success is True
        assert result.credit_score <= 579
        assert result.negative_items_count >= 2  # Collections + charge-off
        assert result.collections_count >= 1

    def test_sandbox_pull_soft(self, consumer_excellent):
        with EquifaxClient(sandbox=True) as client:
            result = client.pull_report(consumer_excellent, PullType.SOFT)

        assert result.success is True
        assert result.pull_type == PullType.SOFT
        assert result.bureau == BureauName.EQUIFAX

    def test_sandbox_file_dispute(self, dispute_request):
        with EquifaxClient(sandbox=True) as client:
            result = client.file_dispute(dispute_request)

        assert result.success is True
        assert result.bureau == BureauName.EQUIFAX
        assert result.confirmation_number.startswith("SANDBOX-DISP-EQU-")
        assert result.filed_at is not None
        assert result.expected_response_by is not None
        # 30 days per FCRA
        delta = result.expected_response_by - result.filed_at
        assert 29 <= delta.days <= 31

    def test_sandbox_dispute_status(self, dispute_request):
        with EquifaxClient(sandbox=True) as client:
            file_result = client.file_dispute(dispute_request)
            status_result = client.get_dispute_status(file_result.confirmation_number)

        assert status_result.success is True
        assert status_result.bureau == BureauName.EQUIFAX
        assert status_result.confirmation_number == file_result.confirmation_number
        assert status_result.status in list(DisputeStatus)
        assert status_result.checked_at is not None

    def test_sandbox_report_has_tradeline_data(self, consumer_poor):
        with EquifaxClient(sandbox=True) as client:
            result = client.pull_report(consumer_poor, PullType.FULL)

        tradelines = result.parsed_data.get("tradelines", [])
        assert len(tradelines) > 0
        for tl in tradelines:
            assert "creditor_name" in tl
            assert "status" in tl
            assert "is_negative" in tl

    def test_context_manager_closes_client(self, consumer_excellent):
        with EquifaxClient(sandbox=True) as client:
            result = client.pull_report(consumer_excellent)
        # After context exit, client should be closed (no error means clean exit)
        assert result.success is True

    def test_report_reference_number_is_unique(self, consumer_excellent):
        with EquifaxClient(sandbox=True) as client:
            r1 = client.pull_report(consumer_excellent)
            r2 = client.pull_report(consumer_excellent)

        assert r1.reference_number != r2.reference_number


# ─────────────────────────────────────────────────────────
# Experian Client Tests
# ─────────────────────────────────────────────────────────

class TestExperianClient:

    def test_sandbox_pull_excellent_credit(self, consumer_excellent):
        with ExperianClient(sandbox=True) as client:
            result = client.pull_report(consumer_excellent, PullType.FULL)

        assert result.success is True
        assert result.bureau == BureauName.EXPERIAN
        assert result.credit_score >= 750

    def test_sandbox_pull_poor_credit(self, consumer_poor):
        with ExperianClient(sandbox=True) as client:
            result = client.pull_report(consumer_poor, PullType.FULL)

        assert result.success is True
        assert result.credit_score <= 579
        assert result.negative_items_count >= 2

    def test_sandbox_file_dispute(self, dispute_request):
        with ExperianClient(sandbox=True) as client:
            result = client.file_dispute(dispute_request)

        assert result.success is True
        assert result.bureau == BureauName.EXPERIAN
        assert result.confirmation_number.startswith("SANDBOX-DISP-EXP-")

    def test_sandbox_dispute_status(self, dispute_request):
        with ExperianClient(sandbox=True) as client:
            file_result = client.file_dispute(dispute_request)
            status_result = client.get_dispute_status(file_result.confirmation_number)

        assert status_result.success is True
        assert status_result.bureau == BureauName.EXPERIAN


# ─────────────────────────────────────────────────────────
# TransUnion Client Tests
# ─────────────────────────────────────────────────────────

class TestTransUnionClient:

    def test_sandbox_pull_excellent_credit(self, consumer_excellent):
        with TransUnionClient(sandbox=True) as client:
            result = client.pull_report(consumer_excellent, PullType.FULL)

        assert result.success is True
        assert result.bureau == BureauName.TRANSUNION
        assert result.credit_score >= 750

    def test_sandbox_pull_all_types(self, consumer_fair):
        for pull_type in [PullType.FULL, PullType.SOFT, PullType.MONITORING]:
            with TransUnionClient(sandbox=True) as client:
                result = client.pull_report(consumer_fair, pull_type)
            assert result.success is True
            assert result.pull_type == pull_type

    def test_sandbox_file_dispute(self, dispute_request):
        with TransUnionClient(sandbox=True) as client:
            result = client.file_dispute(dispute_request)

        assert result.success is True
        assert result.bureau == BureauName.TRANSUNION
        assert result.confirmation_number.startswith("SANDBOX-DISP-TRA-")

    def test_sandbox_dispute_status(self, dispute_request):
        with TransUnionClient(sandbox=True) as client:
            file_result = client.file_dispute(dispute_request)
            status_result = client.get_dispute_status(file_result.confirmation_number)

        assert status_result.success is True
        assert status_result.bureau == BureauName.TRANSUNION


# ─────────────────────────────────────────────────────────
# iSoftPull Client Tests
# ─────────────────────────────────────────────────────────

class TestISoftPullClient:

    def test_sandbox_tri_merge_excellent(self, consumer_excellent):
        with ISoftPullClient(sandbox=True) as client:
            results = client.pull_tri_merge(consumer_excellent)

        assert BureauName.EQUIFAX in results
        assert BureauName.EXPERIAN in results
        assert BureauName.TRANSUNION in results

        for bureau, result in results.items():
            assert result.success is True
            assert result.bureau == bureau
            assert result.pull_type == PullType.SOFT
            assert result.credit_score >= 750

    def test_sandbox_tri_merge_poor(self, consumer_poor):
        with ISoftPullClient(sandbox=True) as client:
            results = client.pull_tri_merge(consumer_poor)

        for bureau, result in results.items():
            assert result.credit_score is not None
            assert result.credit_score <= 579

    def test_sandbox_monitoring_returns_all_bureaus(self, consumer_fair):
        with ISoftPullClient(sandbox=True) as client:
            scores = client.pull_monitoring(consumer_fair)

        assert BureauName.EQUIFAX in scores
        assert BureauName.EXPERIAN in scores
        assert BureauName.TRANSUNION in scores
        for bureau, score in scores.items():
            assert score is not None
            assert 300 <= score <= 850

    def test_monitoring_scores_slightly_different_per_bureau(self, consumer_excellent):
        with ISoftPullClient(sandbox=True) as client:
            scores = client.pull_monitoring(consumer_excellent)

        eq = scores[BureauName.EQUIFAX]
        ex = scores[BureauName.EXPERIAN]
        tu = scores[BureauName.TRANSUNION]

        # Scores should differ slightly between bureaus (realistic)
        assert not (eq == ex == tu)

    def test_dispute_filing_not_supported(self, dispute_request):
        with ISoftPullClient(sandbox=True) as client:
            with pytest.raises(NotImplementedError):
                client.file_dispute(dispute_request)


# ─────────────────────────────────────────────────────────
# Cross-Bureau Consistency Tests
# ─────────────────────────────────────────────────────────

class TestCrossBureauConsistency:

    def test_all_bureaus_same_scenario_for_excellent_consumer(self, consumer_excellent):
        """All bureaus should return excellent credit for the same consumer."""
        clients = [
            (BureauName.EQUIFAX, EquifaxClient(sandbox=True)),
            (BureauName.EXPERIAN, ExperianClient(sandbox=True)),
            (BureauName.TRANSUNION, TransUnionClient(sandbox=True)),
        ]

        for expected_bureau, client in clients:
            with client:
                result = client.pull_report(consumer_excellent, PullType.FULL)
            assert result.credit_score >= 750, f"{expected_bureau} should show excellent credit"
            assert result.negative_items_count == 0, f"{expected_bureau} should have no negatives"

    def test_all_bureaus_file_dispute(self, dispute_request):
        """All bureaus should accept dispute filing in sandbox."""
        clients = [
            EquifaxClient(sandbox=True),
            ExperianClient(sandbox=True),
            TransUnionClient(sandbox=True),
        ]

        for client in clients:
            with client:
                result = client.file_dispute(dispute_request)
            assert result.success is True
            assert result.confirmation_number is not None
            assert result.expected_response_by > result.filed_at

    def test_fcra_30_day_window_all_bureaus(self, dispute_request):
        """Every bureau must give 30-day response window per FCRA."""
        for ClientClass in [EquifaxClient, ExperianClient, TransUnionClient]:
            with ClientClass(sandbox=True) as client:
                result = client.file_dispute(dispute_request)
            days = (result.expected_response_by - result.filed_at).days
            assert days == 30, f"{ClientClass.__name__} must use 30-day FCRA window"


# ─────────────────────────────────────────────────────────
# Edge Case Tests
# ─────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_ssn_boundary_excellent_upper(self):
        """SSN 3333 is the exact boundary of excellent credit."""
        consumer = ConsumerIdentity(
            first_name="Test", last_name="User", ssn="000-00-3333",
            date_of_birth="1990-01-01", address_line1="1 Test St",
            city="Test", state="NC", zip_code="00000",
        )
        with EquifaxClient(sandbox=True) as client:
            result = client.pull_report(consumer)
        assert result.credit_score >= 750

    def test_ssn_boundary_fair_lower(self):
        """SSN 3334 is the start of fair credit."""
        consumer = ConsumerIdentity(
            first_name="Test", last_name="User", ssn="000-00-3334",
            date_of_birth="1990-01-01", address_line1="1 Test St",
            city="Test", state="NC", zip_code="00000",
        )
        with EquifaxClient(sandbox=True) as client:
            result = client.pull_report(consumer)
        assert 580 <= result.credit_score <= 699

    def test_dispute_explanation_long_text(self, consumer_excellent):
        """Dispute with very long explanation should be accepted."""
        long_explanation = "A" * 5000  # Longer than some bureau limits

        request = DisputeFilingRequest(
            consumer=consumer_excellent,
            tradeline_id_at_bureau="TL-99999",
            creditor_name="Test Creditor",
            account_number_masked="****9999",
            dispute_reason_code="inaccurate",
            dispute_explanation=long_explanation,
        )

        with EquifaxClient(sandbox=True) as client:
            result = client.file_dispute(request)

        assert result.success is True  # Sandbox truncates, doesn't fail

    def test_monitoring_pull_type(self, consumer_excellent):
        """Monitoring pull type is supported."""
        with EquifaxClient(sandbox=True) as client:
            result = client.pull_report(consumer_excellent, PullType.MONITORING)

        assert result.success is True
        assert result.pull_type == PullType.MONITORING
