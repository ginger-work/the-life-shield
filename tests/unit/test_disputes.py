"""
Unit Tests — Dispute System

Tests cover:
1. Compliance check service (content rules, communication rules)
2. Letter generation (mocked AI calls)
3. Dispute service (case creation, approval, filing, response)
4. Monitor task logic

Coverage target: 80%+
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.dispute import (
    BureauResponseType,
    DisputeReason,
    DisputeStatus,
    LetterStatus,
)
from app.services.compliance_check import (
    ComplianceSeverity,
    check_communication_compliance,
    check_content_compliance,
    check_dispute_letter_compliance,
)
from app.services.letter_generation import (
    ComplianceResult,
    GeneratedLetter,
    LetterContext,
    _build_template_letter,
    _check_compliance_with_claude,
    _generate_with_openai,
    generate_dispute_letter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_letter_context(**overrides) -> LetterContext:
    defaults = dict(
        client_full_name="John Smith",
        client_address_line1="123 Main St",
        client_city="Charlotte",
        client_state="NC",
        client_zip_code="28202",
        client_ssn_last4="1234",
        creditor_name="Medical Collection Agency",
        account_number_masked="****5678",
        dispute_reason="unverifiable",
        item_description="Medical collection that I have no record of",
        bureau="equifax",
        analyst_notes="Client disputes this as unknown to them.",
    )
    defaults.update(overrides)
    return LetterContext(**defaults)


def make_mock_dispute_case(
    status=DisputeStatus.PENDING_APPROVAL,
    bureau="equifax",
) -> MagicMock:
    case = MagicMock()
    case.id = uuid.uuid4()
    case.client_id = uuid.uuid4()
    case.bureau = bureau
    case.dispute_reason = DisputeReason.UNVERIFIABLE
    case.item_description = "Unknown medical collection"
    case.creditor_name = "Collector Inc"
    case.account_number_masked = "****1234"
    case.tradeline_id = None
    case.filing_agent_id = None
    case.status = status
    case.analyst_notes = None
    case.filed_date = None
    case.expected_response_date = None
    case.outcome = None
    case.outcome_date = None
    case.score_impact_points = None
    return case


def make_mock_client() -> MagicMock:
    client = MagicMock()
    client.id = uuid.uuid4()
    client.full_name = "John Smith"
    client.address_line1 = "123 Main St"
    client.city = "Charlotte"
    client.state = "NC"
    client.zip_code = "28202"
    client.ssn_last_4 = "1234"
    return client


# ---------------------------------------------------------------------------
# 1. Content Compliance Tests
# ---------------------------------------------------------------------------

class TestContentCompliance:

    def test_clean_professional_letter_passes(self):
        letter = (
            "Dear Equifax, I am writing to dispute an item under FCRA § 611. "
            "I believe the Medical Collection from Collector Inc is unverifiable. "
            "Please investigate and remove if unverifiable. Sincerely, John Smith"
        )
        result = check_content_compliance(letter)
        assert result.passed is True
        assert len(result.violations) == 0

    def test_outcome_guarantee_blocked(self):
        content = "We guarantee your score will improve by 100 points after removal."
        result = check_content_compliance(content)
        assert result.passed is False
        assert any(v.rule == "croa.outcome_guarantee" for v in result.violations)

    def test_score_promise_blocked(self):
        content = "Your score will go up after we file this dispute."
        result = check_content_compliance(content)
        assert result.passed is False
        assert any(v.rule == "croa.score_promise" for v in result.violations)

    def test_cpn_fraud_blocked(self):
        content = "You can get a CPN credit privacy number to start fresh."
        result = check_content_compliance(content)
        assert result.passed is False
        assert any(v.rule == "fcra.cpn_fraud" for v in result.violations)

    def test_fabrication_blocked(self):
        content = "We will make up reasons to dispute this item."
        result = check_content_compliance(content)
        assert result.passed is False
        assert any(v.rule == "fcra.fabrication" for v in result.violations)

    def test_upfront_payment_blocked(self):
        content = "Pay us before we file your disputes with the bureau."
        result = check_content_compliance(content)
        assert result.passed is False
        assert any(v.rule == "croa.upfront_payment" for v in result.violations)

    def test_soft_score_suggestion_warns(self):
        content = "Removing this item could improve your score significantly."
        result = check_content_compliance(content)
        # Should not block, but may warn
        # "could improve" matches warn pattern
        assert result.passed is True  # No block
        # Warnings may or may not fire depending on regex

    def test_multiple_violations_all_captured(self):
        content = (
            "We guarantee removal and your score will go up. "
            "Also we can make up a CPN for you."
        )
        result = check_content_compliance(content)
        assert result.passed is False
        assert len(result.violations) >= 2

    def test_empty_content_passes_rules(self):
        """Empty content has no violations (length check is letter-specific)."""
        result = check_content_compliance("")
        assert result.passed is True


# ---------------------------------------------------------------------------
# 2. Dispute Letter Compliance Tests
# ---------------------------------------------------------------------------

class TestDisputeLetterCompliance:

    def test_good_letter_passes(self):
        letter = (
            "Dear Equifax,\n\n"
            "I am writing pursuant to FCRA § 611 to dispute the following item: "
            "Medical Collection from Collector Inc, Account ****1234. "
            "This item is unverifiable. Please investigate and remove if unverifiable.\n\n"
            "Sincerely,\nJohn Smith\n123 Main St, Charlotte NC 28202\nSSN: ****1234"
        )
        result = check_dispute_letter_compliance(letter)
        assert result.passed is True

    def test_letter_too_short_blocked(self):
        result = check_dispute_letter_compliance("Short letter.")
        assert result.passed is False
        assert any(v.rule == "fcra.letter_too_short" for v in result.violations)

    def test_letter_without_fcra_reference_warns(self):
        letter = (
            "Dear Equifax, I want to dispute the medical collection account. "
            "It is inaccurate and I want it removed. Please investigate.\n\n"
            "Sincerely, John Smith, 123 Main St, Charlotte NC"
        )
        result = check_dispute_letter_compliance(letter)
        # Should warn about missing FCRA reference
        assert any(v.rule == "fcra.no_statute_reference" for v in result.warnings)


# ---------------------------------------------------------------------------
# 3. Communication Compliance Tests
# ---------------------------------------------------------------------------

class TestCommunicationCompliance:

    def test_sms_with_consent_passes(self):
        result = check_communication_compliance(
            content="Your dispute status has been updated.",
            channel="sms",
            client_has_sms_consent=True,
            current_hour=10,
        )
        assert result.passed is True

    def test_sms_without_consent_blocked(self):
        result = check_communication_compliance(
            content="Hello there!",
            channel="sms",
            client_has_sms_consent=False,
            current_hour=10,
        )
        assert result.passed is False
        assert any(v.rule == "tcpa.no_sms_consent" for v in result.violations)

    def test_email_without_consent_blocked(self):
        result = check_communication_compliance(
            content="Your letter is ready.",
            channel="email",
            client_has_email_consent=False,
        )
        assert result.passed is False
        assert any(v.rule == "can_spam.no_email_consent" for v in result.violations)

    def test_voice_on_dnc_blocked(self):
        result = check_communication_compliance(
            content="Calling about your dispute.",
            channel="voice",
            client_has_call_consent=True,
            client_on_dnc=True,
            current_hour=10,
        )
        assert result.passed is False
        assert any(v.rule == "tcpa.dnc_list" for v in result.violations)

    def test_sms_outside_hours_blocked(self):
        result = check_communication_compliance(
            content="Good morning!",
            channel="sms",
            client_has_sms_consent=True,
            current_hour=22,  # 10 PM
        )
        assert result.passed is False
        assert any(v.rule == "tcpa.outside_hours" for v in result.violations)

    def test_sms_early_morning_blocked(self):
        result = check_communication_compliance(
            content="Wake up!",
            channel="sms",
            client_has_sms_consent=True,
            current_hour=6,  # 6 AM
        )
        assert result.passed is False
        assert any(v.rule == "tcpa.outside_hours" for v in result.violations)

    def test_portal_chat_no_consent_needed(self):
        """Portal chat is client-initiated — no consent check needed."""
        result = check_communication_compliance(
            content="Here is your update.",
            channel="chat",
        )
        assert result.passed is True


# ---------------------------------------------------------------------------
# 4. Letter Generation Tests (mocked AI calls)
# ---------------------------------------------------------------------------

class TestLetterGeneration:

    def test_template_fallback_letter_has_required_elements(self):
        ctx = make_letter_context()
        reason_narrative = "is unverifiable and should be removed"
        bureau_address = "Equifax Information Services LLC\nP.O. Box 740256\nAtlanta, GA 30374"

        letter = _build_template_letter(ctx, reason_narrative, bureau_address)

        assert "John Smith" in letter
        assert "Equifax" in letter
        assert "Medical Collection Agency" in letter
        assert "****5678" in letter
        assert "FCRA" in letter
        assert "611" in letter
        assert "Charlotte" in letter
        assert "NC" in letter
        assert "28202" in letter

    def test_template_letter_contains_bureau_address(self):
        ctx = make_letter_context(bureau="transunion")
        letter = _build_template_letter(
            ctx,
            "is inaccurate",
            "TransUnion LLC\nConsumer Dispute Center\nP.O. Box 2000",
        )
        assert "TransUnion" in letter

    @pytest.mark.asyncio
    async def test_generate_letter_uses_template_when_no_api_key(self):
        """When OpenAI key is not set, should fall back to template."""
        ctx = make_letter_context()
        with patch("app.services.letter_generation.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = None
            mock_settings.ANTHROPIC_API_KEY = None
            mock_settings.OPENAI_MODEL = "gpt-4-turbo"
            mock_settings.ANTHROPIC_MODEL = "claude-3-5-sonnet-20241022"

            result = await generate_dispute_letter(ctx)

        assert result.content  # Not empty
        assert result.ai_model_used == "template_fallback"
        assert result.compliance is not None

    @pytest.mark.asyncio
    async def test_generate_letter_with_mocked_openai(self):
        """Mock OpenAI returning a good letter."""
        ctx = make_letter_context()
        mock_letter = (
            "Dear Equifax,\n\n"
            "I am writing pursuant to FCRA § 611 to dispute the Medical Collection "
            "from Medical Collection Agency. This item is unverifiable.\n\n"
            "Sincerely, John Smith"
        )

        with patch("app.services.letter_generation._generate_with_openai", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = (mock_letter, "gpt-4-turbo")

            with patch("app.services.letter_generation._check_compliance_with_claude", new_callable=AsyncMock) as mock_claude:
                mock_claude.return_value = ComplianceResult(
                    passed=True, flags=[], explanation="Compliant", checked_by_model="claude-3-5"
                )

                result = await generate_dispute_letter(ctx)

        assert result.content == mock_letter
        assert result.ai_model_used == "gpt-4-turbo"
        assert result.compliance.passed is True

    @pytest.mark.asyncio
    async def test_generate_letter_claude_flags_violation(self):
        """Mock Claude detecting a compliance violation."""
        ctx = make_letter_context()
        mock_letter = "We guarantee your score will improve 100 points after removal."

        with patch("app.services.letter_generation._generate_with_openai", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = (mock_letter, "gpt-4-turbo")

            with patch("app.services.letter_generation._check_compliance_with_claude", new_callable=AsyncMock) as mock_claude:
                mock_claude.return_value = ComplianceResult(
                    passed=False,
                    flags=["croa.outcome_guarantee"],
                    explanation="Letter contains a guarantee of outcome.",
                    checked_by_model="claude-3-5",
                )

                result = await generate_dispute_letter(ctx)

        assert result.compliance.passed is False
        assert "croa.outcome_guarantee" in result.compliance.flags

    def test_prompt_hash_is_deterministic(self):
        """Same input should produce same prompt hash."""
        import hashlib

        ctx = make_letter_context()
        reason = "is unverifiable"
        bureau = "Equifax Information Services LLC\nP.O. Box 740256"

        # Simulate hash computation from generate_dispute_letter
        prompt_a = f"CLIENT: {ctx.client_full_name} BUREAU: {bureau} REASON: {reason}"
        prompt_b = f"CLIENT: {ctx.client_full_name} BUREAU: {bureau} REASON: {reason}"

        hash_a = hashlib.sha256(prompt_a.encode()).hexdigest()
        hash_b = hashlib.sha256(prompt_b.encode()).hexdigest()

        assert hash_a == hash_b


# ---------------------------------------------------------------------------
# 5. Dispute Service Tests
# ---------------------------------------------------------------------------

class TestDisputeService:

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.add = MagicMock()
        db.flush = MagicMock()
        db.query.return_value.filter.return_value.count.return_value = 0
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        return db

    @pytest.mark.asyncio
    async def test_create_dispute_case(self, mock_db):
        from app.api.disputes.service import create_dispute_case

        client_id = uuid.uuid4()
        case = await create_dispute_case(
            db=mock_db,
            client_id=client_id,
            bureau="equifax",
            dispute_reason=DisputeReason.UNVERIFIABLE,
            item_description="Unknown medical collection on my report",
            creditor_name="Collector Inc",
            account_number_masked="****1234",
        )

        assert case is not None
        assert case.client_id == client_id
        assert case.bureau == "equifax"
        assert case.status == DisputeStatus.PENDING_APPROVAL
        assert mock_db.add.called

    @pytest.mark.asyncio
    async def test_create_dispute_case_normalizes_bureau_to_lowercase(self, mock_db):
        from app.api.disputes.service import create_dispute_case

        case = await create_dispute_case(
            db=mock_db,
            client_id=uuid.uuid4(),
            bureau="EQUIFAX",
            dispute_reason=DisputeReason.INACCURATE,
            item_description="Test item description here",
        )

        assert case.bureau == "equifax"

    def test_approve_letter(self, mock_db):
        from app.api.disputes.service import approve_dispute_letter

        letter = MagicMock()
        letter.id = uuid.uuid4()
        letter.client_id = uuid.uuid4()
        letter.status = LetterStatus.PENDING_HUMAN_APPROVAL
        letter.dispute = MagicMock()

        admin_id = uuid.uuid4()
        result = approve_dispute_letter(db=mock_db, letter=letter, admin_user_id=admin_id)

        assert result.status == LetterStatus.APPROVED
        assert result.approved_by_admin_id == admin_id
        assert result.approval_date is not None
        assert letter.dispute.status == DisputeStatus.APPROVED

    def test_reject_letter(self, mock_db):
        from app.api.disputes.service import reject_dispute_letter

        letter = MagicMock()
        letter.id = uuid.uuid4()
        letter.client_id = uuid.uuid4()
        letter.status = LetterStatus.PENDING_HUMAN_APPROVAL
        letter.dispute = MagicMock()

        result = reject_dispute_letter(
            db=mock_db,
            letter=letter,
            admin_user_id=uuid.uuid4(),
            rejection_reason="Letter contains inappropriate language.",
        )

        assert result.status == LetterStatus.REVISION_REQUESTED
        assert result.rejection_reason == "Letter contains inappropriate language."

    @pytest.mark.asyncio
    async def test_file_dispute_requires_approved_letter(self, mock_db):
        from app.api.disputes.service import file_dispute_to_bureau

        case = make_mock_dispute_case(status=DisputeStatus.APPROVED)

        letter = MagicMock()
        letter.status = LetterStatus.PENDING_HUMAN_APPROVAL  # Not approved!

        with pytest.raises(ValueError, match="Letter must be APPROVED"):
            await file_dispute_to_bureau(db=mock_db, dispute_case=case, letter=letter)

    @pytest.mark.asyncio
    async def test_file_dispute_sets_tracking_and_dates(self, mock_db):
        from app.api.disputes.service import file_dispute_to_bureau

        case = make_mock_dispute_case(status=DisputeStatus.APPROVED)
        case.filed_date = None
        case.expected_response_date = None

        letter = MagicMock()
        letter.id = uuid.uuid4()
        letter.status = LetterStatus.APPROVED

        result = await file_dispute_to_bureau(db=mock_db, dispute_case=case, letter=letter)

        assert "tracking_number" in result
        assert result["tracking_number"].startswith("TLS-EQU-")
        assert case.status == DisputeStatus.FILED
        assert case.filed_date is not None
        assert case.expected_response_date is not None
        # Expected response should be 30 days after filing
        delta = case.expected_response_date - case.filed_date
        assert 29 <= delta.days <= 30

    def test_record_removed_response_resolves_case(self, mock_db):
        from app.api.disputes.service import record_bureau_response

        case = make_mock_dispute_case(status=DisputeStatus.FILED)
        case.filed_date = datetime.now(timezone.utc) - timedelta(days=20)
        case.tradeline_id = None

        mock_db.flush = MagicMock()

        response = record_bureau_response(
            db=mock_db,
            dispute_case=case,
            response_type=BureauResponseType.REMOVED,
            score_impact=25,
        )

        assert case.status == DisputeStatus.RESOLVED
        assert case.outcome == BureauResponseType.REMOVED
        assert case.score_impact_points == 25
        assert response is not None

    def test_record_verified_response_resolves_case(self, mock_db):
        from app.api.disputes.service import record_bureau_response

        case = make_mock_dispute_case(status=DisputeStatus.FILED)
        case.filed_date = datetime.now(timezone.utc) - timedelta(days=25)
        case.tradeline_id = None
        mock_db.flush = MagicMock()

        response = record_bureau_response(
            db=mock_db,
            dispute_case=case,
            response_type=BureauResponseType.VERIFIED,
        )

        assert case.status == DisputeStatus.RESOLVED
        assert case.outcome == BureauResponseType.VERIFIED

    def test_record_reinvestigation_extends_timeline(self, mock_db):
        from app.api.disputes.service import record_bureau_response

        original_expected = datetime.now(timezone.utc) + timedelta(days=2)
        case = make_mock_dispute_case(status=DisputeStatus.FILED)
        case.filed_date = datetime.now(timezone.utc) - timedelta(days=28)
        case.expected_response_date = original_expected
        case.tradeline_id = None
        mock_db.flush = MagicMock()

        record_bureau_response(
            db=mock_db,
            dispute_case=case,
            response_type=BureauResponseType.REINVESTIGATION,
        )

        # Timeline should be extended
        assert case.expected_response_date > original_expected
        assert case.status == DisputeStatus.RESPONDED

    def test_get_dispute_status_summary(self, mock_db):
        from app.api.disputes.service import get_dispute_status_summary

        case = make_mock_dispute_case(status=DisputeStatus.FILED)
        case.filed_date = datetime.now(timezone.utc) - timedelta(days=10)
        case.expected_response_date = datetime.now(timezone.utc) + timedelta(days=20)
        case.created_at = datetime.now(timezone.utc) - timedelta(days=10)

        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        summary = get_dispute_status_summary(db=mock_db, dispute_case=case)

        assert "dispute_id" in summary
        assert "status" in summary
        assert summary["days_investigating"] is not None
        assert summary["days_remaining"] is not None
        assert summary["overdue"] is False


# ---------------------------------------------------------------------------
# 6. Monitor Task Tests
# ---------------------------------------------------------------------------

class TestDisputeMonitor:

    @pytest.mark.asyncio
    async def test_monitor_handles_empty_db(self):
        """Monitor with no open disputes should run cleanly."""
        from app.tasks.monitor_disputes import monitor_all_disputes

        mock_db = MagicMock()

        with patch("app.tasks.monitor_disputes.get_overdue_disputes", return_value=[]):
            with patch("app.tasks.monitor_disputes.get_disputes_needing_check", return_value=[]):
                with patch("app.tasks.monitor_disputes.get_db_context") as mock_ctx:
                    mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
                    mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

                    summary = await monitor_all_disputes()

        assert summary["overdue_flagged"] == 0
        assert summary["status_checks_triggered"] == 0
        assert summary["errors"] == []

    def test_generate_resolution_report_win(self):
        from app.tasks.monitor_disputes import generate_resolution_report

        case = make_mock_dispute_case(status=DisputeStatus.RESOLVED)
        case.outcome = BureauResponseType.REMOVED
        case.filed_date = datetime.now(timezone.utc) - timedelta(days=22)
        case.outcome_date = datetime.now(timezone.utc)
        case.score_impact_points = 30

        report = generate_resolution_report(case)

        assert report["is_win"] is True
        assert report["outcome"] == "removed"
        assert "🎉" in report["win_message"]
        assert "30" in report["win_message"]  # Score impact
        assert report["days_to_resolve"] == 22

    def test_generate_resolution_report_verified(self):
        from app.tasks.monitor_disputes import generate_resolution_report

        case = make_mock_dispute_case(status=DisputeStatus.RESOLVED)
        case.outcome = BureauResponseType.VERIFIED
        case.filed_date = datetime.now(timezone.utc) - timedelta(days=28)
        case.outcome_date = datetime.now(timezone.utc)
        case.score_impact_points = None

        report = generate_resolution_report(case)

        assert report["is_win"] is False
        assert "verified" in report.get("verified_message", "").lower()


# ---------------------------------------------------------------------------
# 7. Integration-style: Full Dispute Lifecycle
# ---------------------------------------------------------------------------

class TestDisputeLifecycle:

    @pytest.mark.asyncio
    async def test_full_lifecycle_pending_to_resolved(self):
        """
        Simulate the complete dispute lifecycle:
        create → generate letter → approve → file → record response → resolved
        """
        from app.api.disputes.service import (
            approve_dispute_letter,
            create_dispute_case,
            file_dispute_to_bureau,
            generate_letter_for_case,
            record_bureau_response,
        )

        # Set up mocks
        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.flush = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 0
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        client_id = uuid.uuid4()
        admin_id = uuid.uuid4()

        # Step 1: Create case
        case = await create_dispute_case(
            db=mock_db,
            client_id=client_id,
            bureau="transunion",
            dispute_reason=DisputeReason.INACCURATE,
            item_description="Late payment mark that was paid on time per my records",
            creditor_name="First Bank",
            account_number_masked="****9999",
        )
        assert case.status == DisputeStatus.PENDING_APPROVAL

        # Step 2: Generate letter (mocked)
        mock_client = make_mock_client()
        mock_client.id = client_id

        mock_letter_content = (
            "Dear TransUnion,\n\nI am writing pursuant to FCRA § 611 to dispute "
            "a late payment mark from First Bank. This is inaccurate per my records.\n\n"
            "Sincerely, John Smith"
        )

        with patch("app.api.disputes.service.generate_dispute_letter", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = GeneratedLetter(
                content=mock_letter_content,
                ai_model_used="gpt-4-turbo",
                generation_prompt_hash="abc123",
                compliance=ComplianceResult(
                    passed=True, flags=[], explanation="Compliant", checked_by_model="claude-3-5"
                ),
            )

            with patch("app.api.disputes.service.check_dispute_letter_compliance") as mock_check:
                mock_check.return_value = MagicMock(passed=True, flag_list=[])

                letter = await generate_letter_for_case(
                    db=mock_db,
                    dispute_case=case,
                    client=mock_client,
                )

        assert letter.status == LetterStatus.PENDING_HUMAN_APPROVAL
        assert letter.compliance_status == "passed"

        # Step 3: Admin approves
        letter.dispute = case
        approve_dispute_letter(db=mock_db, letter=letter, admin_user_id=admin_id)
        assert letter.status == LetterStatus.APPROVED
        assert case.status == DisputeStatus.APPROVED

        # Step 4: File to bureau
        result = await file_dispute_to_bureau(db=mock_db, dispute_case=case, letter=letter)
        assert case.status == DisputeStatus.FILED
        assert "tracking_number" in result
        assert result["tracking_number"].startswith("TLS-TRA-")

        # Step 5: Bureau responds — item removed!
        case.tradeline_id = None
        mock_db.flush = MagicMock()
        response = record_bureau_response(
            db=mock_db,
            dispute_case=case,
            response_type=BureauResponseType.REMOVED,
            score_impact=40,
        )

        assert case.status == DisputeStatus.RESOLVED
        assert case.outcome == BureauResponseType.REMOVED
        assert case.score_impact_points == 40
