"""
Dispute Service

Orchestrates the complete dispute lifecycle:
1. Create dispute case
2. Generate AI dispute letter
3. Compliance check (FCRA/CROA)
4. Human approval gate (MANDATORY — per spec)
5. File with bureau
6. Monitor status
7. Process bureau response

FCRA Requirements:
- Bureaus must respond within 30 days
- All filings must have paper trail
- Consumer rights must be disclosed
- Complete audit trail mandatory
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.bureaus import (
    BureauName as IntegrationBureauName,
    ConsumerIdentity,
    DisputeFilingRequest,
    DisputeFilingResult,
    DisputeStatusResult,
    EquifaxClient,
    ExperianClient,
    TransUnionClient,
)
from app.models.audit import AuditAction
from app.models.client import ClientProfile, Tradeline
from app.models.dispute import (
    BureauResponse,
    BureauResponseType,
    DisputeCase,
    DisputeLetter,
    DisputeReason,
    DisputeStatus,
    LetterStatus,
)
from app.services.audit_service import log_audit

log = structlog.get_logger(__name__)

# Map bureau string → integration enum
BUREAU_MAP = {
    "equifax": IntegrationBureauName.EQUIFAX,
    "experian": IntegrationBureauName.EXPERIAN,
    "transunion": IntegrationBureauName.TRANSUNION,
}

# Compliance keywords to flag (CROA § 404 — deceptive practices)
COMPLIANCE_FORBIDDEN_PHRASES = [
    "guaranteed",
    "100% removal",
    "remove all",
    "new credit identity",
    "cpn",
    "credit profile number",
    "erase",
    "clean slate",
    "legally remove",
    "guaranteed results",
    "promise to remove",
]

# FCRA boilerplate required in all dispute letters
FCRA_DISCLAIMER = (
    "\n\nThis dispute is submitted pursuant to the Fair Credit Reporting Act (FCRA), "
    "15 U.S.C. § 1681, specifically § 611 (Process of Dispute and Correction). "
    "I request that this matter be investigated and corrected within 30 days as required by law."
)


def _build_bureau_client(bureau: str, sandbox: bool = True):
    """Instantiate the correct bureau client for dispute filing."""
    if bureau == "equifax":
        return EquifaxClient(
            client_id=settings.EQUIFAX_CLIENT_ID,
            client_secret=settings.EQUIFAX_CLIENT_SECRET,
            sandbox=sandbox,
        )
    elif bureau == "experian":
        return ExperianClient(
            client_id=settings.EXPERIAN_CLIENT_ID,
            client_secret=settings.EXPERIAN_CLIENT_SECRET,
            subcode=settings.EXPERIAN_SUBCODE,
            sandbox=sandbox,
        )
    elif bureau == "transunion":
        return TransUnionClient(
            api_key=settings.TRANSUNION_API_KEY,
            api_secret=settings.TRANSUNION_API_SECRET,
            member_code=settings.TRANSUNION_MEMBER_CODE,
            sandbox=sandbox,
        )
    raise ValueError(f"Unknown bureau: {bureau}")


def _compliance_check(letter_content: str) -> tuple[str, list[str]]:
    """
    Check dispute letter content for CROA/FCRA compliance.

    Returns:
        (status, flags) where status is "passed", "flagged"
        and flags is a list of issues found
    """
    content_lower = letter_content.lower()
    flags = []

    for phrase in COMPLIANCE_FORBIDDEN_PHRASES:
        if phrase in content_lower:
            flags.append(f"Forbidden phrase detected: '{phrase}'")

    # Check minimum content requirements
    if len(letter_content.strip()) < 100:
        flags.append("Letter content is too short (minimum 100 characters)")

    if not any(
        keyword in content_lower
        for keyword in ["fcra", "fair credit reporting", "dispute", "inaccurate", "incorrect"]
    ):
        flags.append("Letter does not reference the dispute basis or FCRA")

    status = "flagged" if flags else "passed"
    return status, flags


def _generate_ai_letter(
    client: ClientProfile,
    dispute_case: DisputeCase,
    tradeline: Optional[Tradeline] = None,
) -> str:
    """
    Generate a dispute letter using AI (Anthropic Claude or OpenAI).

    In sandbox mode, generates a template-based letter.
    In production, calls AI API for personalized letter.
    """
    sandbox = settings.is_development or settings.BUREAU_SANDBOX_MODE

    if sandbox:
        # High-quality template for sandbox
        creditor = dispute_case.creditor_name or (tradeline.creditor_name if tradeline else "the above-referenced creditor")
        account_num = dispute_case.account_number_masked or (tradeline.account_number_masked if tradeline else "on file")

        reason_language = {
            DisputeReason.INACCURATE: f"The information reported by {creditor} contains inaccuracies that are negatively impacting my credit score.",
            DisputeReason.NOT_MINE: f"I have no knowledge of this account with {creditor} and have never authorized it.",
            DisputeReason.WRONG_BALANCE: f"The balance reported by {creditor} is incorrect. My records show a different amount.",
            DisputeReason.WRONG_STATUS: f"The account status reported by {creditor} does not accurately reflect the current status of my account.",
            DisputeReason.FRAUDULENT: f"This account with {creditor} was opened as a result of identity theft. I did not authorize this account.",
            DisputeReason.OBSOLETE: f"This account with {creditor} is beyond the 7-year reporting limit established under the FCRA, § 605.",
            DisputeReason.DUPLICATE: f"This account with {creditor} appears to be a duplicate entry on my credit report.",
            DisputeReason.UNVERIFIABLE: f"I have reason to believe that the information reported by {creditor} cannot be verified.",
            DisputeReason.INCOMPLETE: f"The information reported by {creditor} is incomplete and does not accurately represent my credit history.",
        }.get(
            dispute_case.dispute_reason,
            f"The information reported by {creditor} is inaccurate."
        )

        letter = f"""To Whom It May Concern:

I am writing to formally dispute the following information on my credit report as reported by {dispute_case.bureau.upper()}:

Account Name: {creditor}
Account Number: {account_num}

NATURE OF DISPUTE:
{reason_language}

{dispute_case.item_description or ""}

REQUEST:
I respectfully request that you conduct a thorough investigation of this matter and take appropriate corrective action, including but not limited to:
1. Investigating the accuracy of this item
2. Correcting any inaccurate or incomplete information
3. Removing the item if it cannot be verified
4. Sending me written notification of the results of your investigation

Please respond within 30 days as required by the FCRA.
{FCRA_DISCLAIMER}

Sincerely,
{client.full_name}"""
        return letter

    # Production: Call AI API
    try:
        if settings.ANTHROPIC_API_KEY:
            return _generate_letter_claude(client, dispute_case, tradeline)
        elif settings.OPENAI_API_KEY:
            return _generate_letter_openai(client, dispute_case, tradeline)
        else:
            log.warning("No AI API key configured, falling back to template")
            return _generate_ai_letter.__wrapped__(client, dispute_case, tradeline)
    except Exception as exc:
        log.error("ai_letter_generation_failed", error=str(exc))
        raise


def _generate_letter_claude(
    client: ClientProfile,
    dispute_case: DisputeCase,
    tradeline: Optional[Tradeline],
) -> str:
    """Generate dispute letter using Anthropic Claude."""
    try:
        import anthropic

        claude = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        prompt = f"""You are a certified credit repair specialist writing a formal dispute letter.

Client: {client.full_name}
Bureau: {dispute_case.bureau.upper()}
Creditor: {dispute_case.creditor_name}
Account: {dispute_case.account_number_masked}
Dispute Reason: {dispute_case.dispute_reason.value}
Item Description: {dispute_case.item_description or 'See dispute reason'}

Write a professional, legally sound dispute letter that:
1. Clearly identifies the disputed item
2. Explains why the information is inaccurate
3. Cites specific FCRA sections (especially § 611)
4. Requests specific corrective action
5. Sets the 30-day investigation timeline
6. Is firm but professional in tone
7. Does NOT make any guarantees or promises about removal
8. Does NOT contain any language that could be considered deceptive per CROA § 404

Return ONLY the letter text, no additional commentary."""

        message = claude.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        letter = message.content[0].text
        return letter + FCRA_DISCLAIMER
    except Exception as exc:
        raise RuntimeError(f"Claude letter generation failed: {exc}") from exc


def _generate_letter_openai(
    client: ClientProfile,
    dispute_case: DisputeCase,
    tradeline: Optional[Tradeline],
) -> str:
    """Generate dispute letter using OpenAI GPT."""
    try:
        from openai import OpenAI

        openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        prompt = f"""Write a formal credit dispute letter for:
Client: {client.full_name}
Bureau: {dispute_case.bureau.upper()}
Creditor: {dispute_case.creditor_name}
Account: {dispute_case.account_number_masked}
Reason: {dispute_case.dispute_reason.value}

Requirements: FCRA compliant, professional, cites § 611, no guarantees."""

        response = openai_client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200,
        )
        letter = response.choices[0].message.content
        return letter + FCRA_DISCLAIMER
    except Exception as exc:
        raise RuntimeError(f"OpenAI letter generation failed: {exc}") from exc


# ─────────────────────────────────────────────────────────
# Public Service Functions
# ─────────────────────────────────────────────────────────

def create_dispute_case(
    db: Session,
    client: ClientProfile,
    bureau: str,
    dispute_reason: str,
    creditor_name: str,
    account_number_masked: Optional[str] = None,
    item_description: Optional[str] = None,
    tradeline_id: Optional[uuid.UUID] = None,
    priority_score: int = 5,
    analyst_notes: Optional[str] = None,
    actor_user_id: Optional[uuid.UUID] = None,
    correlation_id: Optional[str] = None,
) -> DisputeCase:
    """
    Create a new dispute case.
    Status starts as PENDING_APPROVAL — no filing without human sign-off.

    Args:
        db: Database session
        client: Client profile
        bureau: "equifax", "experian", or "transunion"
        dispute_reason: DisputeReason enum value string
        creditor_name: Name of the creditor being disputed
        account_number_masked: Last 4 digits or masked account number
        item_description: Human-readable description of disputed item
        tradeline_id: Optional link to existing Tradeline record
        priority_score: 1-10 priority (higher = more impactful)
        analyst_notes: Credit analyst's notes
        actor_user_id: User creating this dispute
        correlation_id: Request correlation ID

    Returns:
        The created DisputeCase
    """
    corr_id = correlation_id or str(uuid.uuid4())

    try:
        reason_enum = DisputeReason(dispute_reason)
    except ValueError:
        raise ValueError(f"Invalid dispute reason: {dispute_reason}. Must be one of: {[r.value for r in DisputeReason]}")

    case = DisputeCase(
        client_id=client.id,
        bureau=bureau.lower(),
        dispute_reason=reason_enum,
        creditor_name=creditor_name,
        account_number_masked=account_number_masked,
        item_description=item_description,
        tradeline_id=tradeline_id,
        status=DisputeStatus.PENDING_APPROVAL,
        priority_score=priority_score,
        analyst_notes=analyst_notes,
    )

    db.add(case)
    db.flush()  # Get ID

    log_audit(
        db,
        AuditAction.DISPUTE_CREATED,
        actor_user_id=actor_user_id,
        actor_type="user" if actor_user_id else "system",
        subject_type="dispute",
        subject_id=case.id,
        client_id=client.id,
        description=f"Dispute case created for {creditor_name} at {bureau}",
        metadata={
            "dispute_id": str(case.id),
            "bureau": bureau,
            "reason": dispute_reason,
            "creditor": creditor_name,
            "priority": priority_score,
        },
        correlation_id=corr_id,
    )

    log.info(
        "dispute_case_created",
        dispute_id=str(case.id),
        bureau=bureau,
        client_id=str(client.id),
    )

    return case


def generate_dispute_letter(
    db: Session,
    dispute_case: DisputeCase,
    client: ClientProfile,
    tradeline: Optional[Tradeline] = None,
    actor_agent_id: Optional[uuid.UUID] = None,
    correlation_id: Optional[str] = None,
) -> DisputeLetter:
    """
    Generate an AI-powered dispute letter for a dispute case.
    Runs compliance check automatically.
    Letter starts as PENDING_HUMAN_APPROVAL — admin must approve before filing.

    Args:
        db: Database session
        dispute_case: The dispute case to generate a letter for
        client: Client profile (for letter personalization)
        tradeline: Optional tradeline record (for additional context)
        actor_agent_id: AI agent generating the letter
        correlation_id: Request correlation ID

    Returns:
        The created DisputeLetter
    """
    corr_id = correlation_id or str(uuid.uuid4())

    # Check if there's already an approved letter (don't regenerate)
    existing_approved = (
        db.query(DisputeLetter)
        .filter(
            DisputeLetter.dispute_id == dispute_case.id,
            DisputeLetter.status == LetterStatus.APPROVED,
        )
        .first()
    )
    if existing_approved:
        log.warning(
            "dispute_letter_already_approved",
            dispute_id=str(dispute_case.id),
        )
        return existing_approved

    # Determine version number
    existing_count = (
        db.query(DisputeLetter)
        .filter(DisputeLetter.dispute_id == dispute_case.id)
        .count()
    )
    version = existing_count + 1

    # Generate letter content
    letter_content = _generate_ai_letter(client, dispute_case, tradeline)

    # Compute prompt hash for reproducibility
    prompt_hash = hashlib.sha256(
        f"{dispute_case.id}{dispute_case.dispute_reason}{dispute_case.creditor_name}".encode()
    ).hexdigest()

    # Run compliance check
    compliance_status, compliance_flags = _compliance_check(letter_content)

    # Determine initial letter status
    if compliance_status == "flagged":
        letter_status = LetterStatus.PENDING_COMPLIANCE
    else:
        letter_status = LetterStatus.PENDING_HUMAN_APPROVAL

    # Determine AI model used
    if settings.is_development or settings.BUREAU_SANDBOX_MODE:
        ai_model = "sandbox-template"
    elif settings.ANTHROPIC_API_KEY:
        ai_model = settings.ANTHROPIC_MODEL
    elif settings.OPENAI_API_KEY:
        ai_model = settings.OPENAI_MODEL
    else:
        ai_model = "template"

    letter = DisputeLetter(
        dispute_id=dispute_case.id,
        client_id=client.id,
        drafting_agent_id=actor_agent_id,
        letter_content=letter_content,
        letter_version=version,
        compliance_status=compliance_status,
        compliance_checked_at=datetime.now(timezone.utc),
        compliance_flags=compliance_flags if compliance_flags else None,
        human_approval_required=True,  # ALWAYS required per spec
        status=letter_status,
        ai_model_used=ai_model,
        generation_prompt_hash=prompt_hash,
    )

    db.add(letter)
    db.flush()

    log_audit(
        db,
        AuditAction.DISPUTE_LETTER_GENERATED,
        actor_agent_id=actor_agent_id,
        actor_type="agent" if actor_agent_id else "system",
        subject_type="dispute",
        subject_id=dispute_case.id,
        client_id=client.id,
        description=f"Dispute letter generated (version {version})",
        metadata={
            "letter_id": str(letter.id),
            "dispute_id": str(dispute_case.id),
            "compliance_status": compliance_status,
            "compliance_flags_count": len(compliance_flags),
            "version": version,
            "ai_model": ai_model,
        },
        correlation_id=corr_id,
    )

    log_audit(
        db,
        AuditAction.DISPUTE_LETTER_COMPLIANCE_CHECKED,
        actor_type="system",
        subject_type="dispute",
        subject_id=dispute_case.id,
        client_id=client.id,
        description=f"Compliance check: {compliance_status}",
        metadata={
            "letter_id": str(letter.id),
            "status": compliance_status,
            "flags": compliance_flags,
        },
        correlation_id=corr_id,
        success=(compliance_status == "passed"),
    )

    log.info(
        "dispute_letter_generated",
        letter_id=str(letter.id),
        dispute_id=str(dispute_case.id),
        compliance=compliance_status,
        version=version,
    )

    return letter


def approve_dispute_letter(
    db: Session,
    letter: DisputeLetter,
    dispute_case: DisputeCase,
    approving_admin_id: uuid.UUID,
    correlation_id: Optional[str] = None,
) -> DisputeLetter:
    """
    Human admin approves a dispute letter for filing.
    This is a MANDATORY step — letters cannot be filed without approval.

    Transitions:
    - Letter status: PENDING_HUMAN_APPROVAL → APPROVED
    - Dispute status: PENDING_APPROVAL → APPROVED

    Args:
        db: Database session
        letter: The DisputeLetter to approve
        dispute_case: The parent DisputeCase
        approving_admin_id: UUID of the admin user approving
        correlation_id: Request correlation ID
    """
    corr_id = correlation_id or str(uuid.uuid4())

    if letter.compliance_status == "flagged":
        raise ValueError(
            "Cannot approve a letter with open compliance flags. "
            "Resolve compliance issues before approving."
        )

    letter.status = LetterStatus.APPROVED
    letter.approved_by_admin_id = approving_admin_id
    letter.approval_date = datetime.now(timezone.utc)

    dispute_case.status = DisputeStatus.APPROVED

    log_audit(
        db,
        AuditAction.DISPUTE_LETTER_APPROVED,
        actor_user_id=approving_admin_id,
        actor_type="user",
        subject_type="dispute",
        subject_id=dispute_case.id,
        client_id=dispute_case.client_id,
        description="Dispute letter approved by admin",
        metadata={
            "letter_id": str(letter.id),
            "dispute_id": str(dispute_case.id),
            "approved_by": str(approving_admin_id),
        },
        correlation_id=corr_id,
    )

    log.info(
        "dispute_letter_approved",
        letter_id=str(letter.id),
        dispute_id=str(dispute_case.id),
        admin_id=str(approving_admin_id),
    )

    return letter


def reject_dispute_letter(
    db: Session,
    letter: DisputeLetter,
    dispute_case: DisputeCase,
    rejecting_admin_id: uuid.UUID,
    reason: str,
    correlation_id: Optional[str] = None,
) -> DisputeLetter:
    """Admin rejects a dispute letter (with required reason)."""
    corr_id = correlation_id or str(uuid.uuid4())

    letter.status = LetterStatus.REVISION_REQUESTED
    letter.rejection_reason = reason

    dispute_case.status = DisputeStatus.REJECTED

    log_audit(
        db,
        AuditAction.DISPUTE_LETTER_REJECTED,
        actor_user_id=rejecting_admin_id,
        actor_type="user",
        subject_type="dispute",
        subject_id=dispute_case.id,
        client_id=dispute_case.client_id,
        description="Dispute letter rejected by admin",
        metadata={
            "letter_id": str(letter.id),
            "rejected_by": str(rejecting_admin_id),
        },
        correlation_id=corr_id,
    )

    return letter


def file_dispute_with_bureau(
    db: Session,
    dispute_case: DisputeCase,
    letter: DisputeLetter,
    client: ClientProfile,
    decrypted_ssn: str,
    tradeline: Optional[Tradeline] = None,
    actor_user_id: Optional[uuid.UUID] = None,
    correlation_id: Optional[str] = None,
) -> DisputeCase:
    """
    File an approved dispute with the credit bureau.

    PREREQUISITES:
    - Dispute case must be in APPROVED status
    - Letter must be in APPROVED status
    - Letter cannot have open compliance flags

    After filing:
    - Dispute status → FILED
    - Letter status → FILED
    - Expected response date set to filed_date + 30 days (FCRA)
    - Full audit trail logged

    Args:
        db: Database session
        dispute_case: The DisputeCase to file
        letter: The approved DisputeLetter
        client: Client profile
        decrypted_ssn: Decrypted SSN for bureau identity verification
        tradeline: Optional tradeline for additional context
        actor_user_id: User filing the dispute
        correlation_id: Request correlation ID
    """
    corr_id = correlation_id or str(uuid.uuid4())
    sandbox = settings.is_development or settings.BUREAU_SANDBOX_MODE

    # Validation
    if dispute_case.status != DisputeStatus.APPROVED:
        raise ValueError(
            f"Dispute must be APPROVED before filing. Current status: {dispute_case.status.value}"
        )
    if letter.status != LetterStatus.APPROVED:
        raise ValueError(
            f"Letter must be APPROVED before filing. Current status: {letter.status.value}"
        )

    # Build consumer identity
    dob_str = (
        client.date_of_birth.strftime("%Y-%m-%d") if client.date_of_birth else ""
    )
    consumer = ConsumerIdentity(
        first_name=client.full_name.split()[0] if client.full_name else "",
        last_name=" ".join(client.full_name.split()[1:]) if client.full_name else "",
        ssn=decrypted_ssn,
        date_of_birth=dob_str,
        address_line1=client.address_line1 or "",
        city=client.city or "",
        state=client.state or "",
        zip_code=client.zip_code or "",
    )

    # Build filing request
    filing_request = DisputeFilingRequest(
        consumer=consumer,
        tradeline_id_at_bureau=str(dispute_case.tradeline_id or ""),
        creditor_name=dispute_case.creditor_name or "",
        account_number_masked=dispute_case.account_number_masked or "",
        dispute_reason_code=dispute_case.dispute_reason.value,
        dispute_explanation=letter.letter_content,
    )

    # Update status to PENDING_FILING
    dispute_case.status = DisputeStatus.PENDING_FILING
    db.flush()

    # File with bureau
    try:
        bureau_client = _build_bureau_client(dispute_case.bureau, sandbox=sandbox)
        result: DisputeFilingResult = bureau_client.file_dispute(
            request=filing_request,
            correlation_id=corr_id,
        )
        bureau_client.close()

        if not result.success:
            dispute_case.status = DisputeStatus.APPROVED  # Revert to allow retry
            log_audit(
                db,
                AuditAction.DISPUTE_FILED,
                actor_user_id=actor_user_id,
                actor_type="user" if actor_user_id else "system",
                subject_type="dispute",
                subject_id=dispute_case.id,
                client_id=client.id,
                description=f"Dispute filing failed at {dispute_case.bureau}",
                metadata={
                    "bureau": dispute_case.bureau,
                    "error": result.error_code,
                },
                correlation_id=corr_id,
                success=False,
                error_code=result.error_code,
                error_message=result.error_message,
            )
            raise RuntimeError(f"Bureau filing failed: {result.error_message}")

        # Update case with filing details
        dispute_case.status = DisputeStatus.FILED
        dispute_case.filed_date = result.filed_at
        dispute_case.expected_response_date = result.expected_response_by

        # Update letter status
        letter.status = LetterStatus.FILED

        log_audit(
            db,
            AuditAction.DISPUTE_FILED,
            actor_user_id=actor_user_id,
            actor_type="user" if actor_user_id else "system",
            subject_type="dispute",
            subject_id=dispute_case.id,
            client_id=client.id,
            description=f"Dispute filed with {dispute_case.bureau} - confirmation {result.confirmation_number}",
            metadata={
                "bureau": dispute_case.bureau,
                "confirmation_number": result.confirmation_number,
                "filed_at": result.filed_at.isoformat(),
                "expected_response_by": result.expected_response_by.isoformat(),
                "sandbox": sandbox,
            },
            correlation_id=corr_id,
        )

        log.info(
            "dispute_filed_successfully",
            dispute_id=str(dispute_case.id),
            bureau=dispute_case.bureau,
            confirmation=result.confirmation_number,
        )

    except Exception as exc:
        if not isinstance(exc, RuntimeError):
            dispute_case.status = DisputeStatus.APPROVED  # Revert
            log_audit(
                db,
                AuditAction.DISPUTE_FILED,
                actor_type="system",
                subject_type="dispute",
                subject_id=dispute_case.id,
                client_id=client.id,
                description=f"Dispute filing exception for {dispute_case.bureau}",
                metadata={"exception": type(exc).__name__},
                correlation_id=corr_id,
                success=False,
                error_message=str(exc)[:500],
            )
        raise

    return dispute_case


def check_dispute_status(
    db: Session,
    dispute_case: DisputeCase,
    confirmation_number: str,
    actor_user_id: Optional[uuid.UUID] = None,
    correlation_id: Optional[str] = None,
) -> DisputeStatusResult:
    """
    Check a dispute's current status with the bureau.
    Updates the dispute case status if changed.

    Args:
        db: Database session
        dispute_case: The dispute case to check
        confirmation_number: Bureau's confirmation number from filing
        actor_user_id: User requesting the status check
        correlation_id: Request correlation ID

    Returns:
        DisputeStatusResult from bureau
    """
    corr_id = correlation_id or str(uuid.uuid4())
    sandbox = settings.is_development or settings.BUREAU_SANDBOX_MODE

    bureau_client = _build_bureau_client(dispute_case.bureau, sandbox=sandbox)
    result = bureau_client.get_dispute_status(
        confirmation_number=confirmation_number,
        correlation_id=corr_id,
    )
    bureau_client.close()

    # Update dispute status based on bureau response
    from app.integrations.bureaus import DisputeStatus as IntegrationStatus

    status_map = {
        IntegrationStatus.SUBMITTED: DisputeStatus.FILED,
        IntegrationStatus.ACKNOWLEDGED: DisputeStatus.FILED,
        IntegrationStatus.INVESTIGATING: DisputeStatus.INVESTIGATING,
        IntegrationStatus.COMPLETED: DisputeStatus.RESPONDED,
        IntegrationStatus.REJECTED: DisputeStatus.REJECTED,
    }

    new_status = status_map.get(result.status)
    if new_status and dispute_case.status != new_status:
        old_status = dispute_case.status
        dispute_case.status = new_status

        log_audit(
            db,
            AuditAction.DISPUTE_STATUS_UPDATED,
            actor_user_id=actor_user_id,
            actor_type="user" if actor_user_id else "system",
            subject_type="dispute",
            subject_id=dispute_case.id,
            client_id=dispute_case.client_id,
            description=f"Dispute status updated: {old_status.value} → {new_status.value}",
            metadata={
                "old_status": old_status.value,
                "new_status": new_status.value,
                "bureau_status": result.status.value,
                "outcome": result.outcome,
            },
            correlation_id=corr_id,
        )

    return result


def record_bureau_response(
    db: Session,
    dispute_case: DisputeCase,
    response_type: str,
    response_content: Optional[str] = None,
    score_impact: Optional[int] = None,
    actor_user_id: Optional[uuid.UUID] = None,
    correlation_id: Optional[str] = None,
) -> BureauResponse:
    """
    Record the bureau's response to a dispute investigation.
    Updates dispute case with outcome and closes the case.

    Args:
        db: Database session
        dispute_case: The dispute case receiving the response
        response_type: BureauResponseType value (removed, updated, verified, etc.)
        response_content: Full text of bureau's response
        score_impact: Estimated score point change
        actor_user_id: User recording the response
        correlation_id: Request correlation ID
    """
    corr_id = correlation_id or str(uuid.uuid4())

    try:
        response_type_enum = BureauResponseType(response_type)
    except ValueError:
        raise ValueError(f"Invalid response type: {response_type}")

    response = BureauResponse(
        dispute_id=dispute_case.id,
        received_date=datetime.now(timezone.utc),
        response_type=response_type_enum,
        response_content=response_content,
        score_impact=score_impact,
    )
    db.add(response)

    # Update dispute case
    dispute_case.status = DisputeStatus.RESOLVED
    dispute_case.outcome = response_type_enum
    dispute_case.outcome_date = datetime.now(timezone.utc)
    dispute_case.response_received_date = datetime.now(timezone.utc)
    if score_impact:
        dispute_case.score_impact_points = score_impact

    log_audit(
        db,
        AuditAction.DISPUTE_RESPONSE_RECEIVED,
        actor_user_id=actor_user_id,
        actor_type="user" if actor_user_id else "system",
        subject_type="dispute",
        subject_id=dispute_case.id,
        client_id=dispute_case.client_id,
        description=f"Bureau response received: {response_type}",
        metadata={
            "response_type": response_type,
            "score_impact": score_impact,
            "dispute_id": str(dispute_case.id),
        },
        correlation_id=corr_id,
    )

    log_audit(
        db,
        AuditAction.DISPUTE_RESOLVED,
        actor_type="system",
        subject_type="dispute",
        subject_id=dispute_case.id,
        client_id=dispute_case.client_id,
        description=f"Dispute resolved with outcome: {response_type}",
        metadata={"outcome": response_type, "score_impact": score_impact},
        correlation_id=corr_id,
    )

    log.info(
        "bureau_response_recorded",
        dispute_id=str(dispute_case.id),
        outcome=response_type,
        score_impact=score_impact,
    )

    return response


def get_disputes_for_client(
    db: Session,
    client_id: uuid.UUID,
    status_filter: Optional[str] = None,
    bureau_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[DisputeCase]:
    """Get disputes for a client with optional filters."""
    query = (
        db.query(DisputeCase)
        .filter(DisputeCase.client_id == client_id)
        .order_by(DisputeCase.created_at.desc())
    )

    if status_filter:
        query = query.filter(DisputeCase.status == DisputeStatus(status_filter))
    if bureau_filter:
        query = query.filter(DisputeCase.bureau == bureau_filter.lower())

    return query.offset(offset).limit(limit).all()


def get_overdue_disputes(db: Session) -> List[DisputeCase]:
    """
    Find disputes where the bureau response is overdue (past 30 days).
    FCRA requires bureau to respond within 30 days.
    These cases may be FCRA violations.
    """
    now = datetime.now(timezone.utc)
    return (
        db.query(DisputeCase)
        .filter(
            DisputeCase.status.in_([DisputeStatus.FILED, DisputeStatus.INVESTIGATING]),
            DisputeCase.expected_response_date < now,
        )
        .order_by(DisputeCase.expected_response_date.asc())
        .all()
    )
