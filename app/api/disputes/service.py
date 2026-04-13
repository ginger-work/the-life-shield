"""
Dispute Service — Core Business Logic

Handles all dispute lifecycle operations:
- Case creation with audit trail
- Letter generation (OpenAI draft + Claude compliance)
- Admin approval workflow
- Bureau filing (simulated/real API)
- Status monitoring
- Resolution handling

FCRA Requirements enforced here:
- Every action is logged to audit_trail (immutable)
- Human approval required before filing
- 30-day investigation tracking
- Bureau response handling
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.audit import AuditAction, AuditTrail
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
from app.services.compliance_check import (
    check_dispute_letter_compliance,
)
from app.services.letter_generation import (
    LetterContext,
    generate_dispute_letter,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log_audit(
    db: Session,
    action: AuditAction,
    subject_type: str,
    subject_id: uuid.UUID,
    client_id: uuid.UUID,
    actor_user_id: Optional[uuid.UUID] = None,
    actor_agent_id: Optional[uuid.UUID] = None,
    actor_type: str = "system",
    description: Optional[str] = None,
    metadata: Optional[dict] = None,
    success: bool = True,
    ip_address: Optional[str] = None,
) -> AuditTrail:
    entry = AuditTrail(
        actor_user_id=actor_user_id,
        actor_agent_id=actor_agent_id,
        actor_type=actor_type,
        subject_type=subject_type,
        subject_id=subject_id,
        client_id=client_id,
        action=action,
        description=description,
        metadata=metadata,
        success=success,
        ip_address=ip_address,
    )
    db.add(entry)
    return entry


# ---------------------------------------------------------------------------
# 1. Create dispute case
# ---------------------------------------------------------------------------

async def create_dispute_case(
    db: Session,
    *,
    client_id: uuid.UUID,
    bureau: str,
    dispute_reason: DisputeReason,
    item_description: str,
    creditor_name: Optional[str] = None,
    account_number_masked: Optional[str] = None,
    tradeline_id: Optional[uuid.UUID] = None,
    filing_agent_id: Optional[uuid.UUID] = None,
    priority_score: int = 5,
    analyst_notes: Optional[str] = None,
    actor_user_id: Optional[uuid.UUID] = None,
    ip_address: Optional[str] = None,
) -> DisputeCase:
    """
    Create a new dispute case in PENDING_APPROVAL status.
    Does NOT generate a letter or file — those are separate steps.
    """
    case = DisputeCase(
        client_id=client_id,
        bureau=bureau.lower(),
        dispute_reason=dispute_reason,
        item_description=item_description,
        creditor_name=creditor_name,
        account_number_masked=account_number_masked,
        tradeline_id=tradeline_id,
        filing_agent_id=filing_agent_id,
        priority_score=priority_score,
        analyst_notes=analyst_notes,
        status=DisputeStatus.PENDING_APPROVAL,
    )
    db.add(case)
    db.flush()  # Get the ID without committing

    _log_audit(
        db=db,
        action=AuditAction.DISPUTE_CREATED,
        subject_type="dispute_case",
        subject_id=case.id,
        client_id=client_id,
        actor_user_id=actor_user_id,
        actor_agent_id=filing_agent_id,
        actor_type="agent" if filing_agent_id else "user",
        description=f"Dispute case created for {creditor_name or 'unknown creditor'} at {bureau}",
        metadata={
            "bureau": bureau,
            "reason": dispute_reason.value,
            "tradeline_id": str(tradeline_id) if tradeline_id else None,
            "priority_score": priority_score,
        },
        ip_address=ip_address,
    )

    logger.info(
        "Dispute case created",
        case_id=str(case.id),
        client_id=str(client_id),
        bureau=bureau,
        reason=dispute_reason.value,
    )
    return case


# ---------------------------------------------------------------------------
# 2. Generate dispute letter for a case
# ---------------------------------------------------------------------------

async def generate_letter_for_case(
    db: Session,
    *,
    dispute_case: DisputeCase,
    client: ClientProfile,
    actor_agent_id: Optional[uuid.UUID] = None,
    actor_user_id: Optional[uuid.UUID] = None,
    ip_address: Optional[str] = None,
) -> DisputeLetter:
    """
    Generate an AI-powered dispute letter for an existing case.
    Runs OpenAI generation + Claude compliance check.
    Stores as draft pending human approval.
    """
    # Build letter context
    ctx = LetterContext(
        client_full_name=client.full_name,
        client_address_line1=client.address_line1 or "",
        client_city=client.city or "",
        client_state=client.state or "",
        client_zip_code=client.zip_code or "",
        client_ssn_last4=client.ssn_last_4 or "XXXX",
        creditor_name=dispute_case.creditor_name or "Unknown Creditor",
        account_number_masked=dispute_case.account_number_masked or "****",
        dispute_reason=dispute_case.dispute_reason.value,
        item_description=dispute_case.item_description or "",
        bureau=dispute_case.bureau,
        analyst_notes=dispute_case.analyst_notes,
    )

    # Determine version number (increment if revising)
    existing_count = (
        db.query(DisputeLetter)
        .filter(DisputeLetter.dispute_id == dispute_case.id)
        .count()
    )
    version = existing_count + 1

    # Generate via AI
    generated = await generate_dispute_letter(ctx)

    # Also run local rule-based compliance check
    local_compliance = check_dispute_letter_compliance(generated.content)

    # Combine compliance results: pass only if both pass
    final_passed = generated.compliance.passed and local_compliance.passed
    all_flags = generated.compliance.flags + local_compliance.flag_list

    compliance_status = "passed" if final_passed else "flagged"
    next_status = (
        LetterStatus.PENDING_HUMAN_APPROVAL
        if final_passed
        else LetterStatus.REVISION_REQUESTED
    )

    letter = DisputeLetter(
        dispute_id=dispute_case.id,
        client_id=dispute_case.client_id,
        drafting_agent_id=actor_agent_id,
        letter_content=generated.content,
        letter_version=version,
        compliance_status=compliance_status,
        compliance_checked_at=datetime.now(timezone.utc),
        compliance_flags=all_flags if all_flags else None,
        human_approval_required=True,
        status=next_status,
        ai_model_used=generated.ai_model_used,
        generation_prompt_hash=generated.generation_prompt_hash,
    )
    db.add(letter)
    db.flush()

    _log_audit(
        db=db,
        action=AuditAction.DISPUTE_LETTER_GENERATED,
        subject_type="dispute_letter",
        subject_id=letter.id,
        client_id=dispute_case.client_id,
        actor_agent_id=actor_agent_id,
        actor_user_id=actor_user_id,
        actor_type="agent" if actor_agent_id else "system",
        description=f"Letter v{version} generated for case {dispute_case.id}. Compliance: {compliance_status}",
        metadata={
            "case_id": str(dispute_case.id),
            "version": version,
            "compliance_status": compliance_status,
            "flags": all_flags,
            "ai_model": generated.ai_model_used,
        },
        ip_address=ip_address,
    )

    _log_audit(
        db=db,
        action=AuditAction.DISPUTE_LETTER_COMPLIANCE_CHECKED,
        subject_type="dispute_letter",
        subject_id=letter.id,
        client_id=dispute_case.client_id,
        actor_type="system",
        description=f"Compliance check result: {compliance_status}",
        metadata={"flags": all_flags, "passed": final_passed},
    )

    logger.info(
        "Dispute letter generated",
        letter_id=str(letter.id),
        case_id=str(dispute_case.id),
        version=version,
        compliance=compliance_status,
    )
    return letter


# ---------------------------------------------------------------------------
# 3. Admin approve / reject letter
# ---------------------------------------------------------------------------

def approve_dispute_letter(
    db: Session,
    *,
    letter: DisputeLetter,
    admin_user_id: uuid.UUID,
    ip_address: Optional[str] = None,
) -> DisputeLetter:
    """Mark a dispute letter as admin-approved. Ready to file."""
    letter.status = LetterStatus.APPROVED
    letter.approved_by_admin_id = admin_user_id
    letter.approval_date = datetime.now(timezone.utc)
    letter.rejection_reason = None

    # Update parent case status
    letter.dispute.status = DisputeStatus.APPROVED

    _log_audit(
        db=db,
        action=AuditAction.DISPUTE_LETTER_APPROVED,
        subject_type="dispute_letter",
        subject_id=letter.id,
        client_id=letter.client_id,
        actor_user_id=admin_user_id,
        actor_type="user",
        description=f"Letter approved by admin {admin_user_id}",
        metadata={"admin_id": str(admin_user_id)},
        ip_address=ip_address,
    )
    logger.info("Dispute letter approved", letter_id=str(letter.id), admin=str(admin_user_id))
    return letter


def reject_dispute_letter(
    db: Session,
    *,
    letter: DisputeLetter,
    admin_user_id: uuid.UUID,
    rejection_reason: str,
    ip_address: Optional[str] = None,
) -> DisputeLetter:
    """Reject a dispute letter. Requires revision before filing."""
    letter.status = LetterStatus.REVISION_REQUESTED
    letter.rejection_reason = rejection_reason

    letter.dispute.status = DisputeStatus.REJECTED

    _log_audit(
        db=db,
        action=AuditAction.DISPUTE_LETTER_REJECTED,
        subject_type="dispute_letter",
        subject_id=letter.id,
        client_id=letter.client_id,
        actor_user_id=admin_user_id,
        actor_type="user",
        description=f"Letter rejected: {rejection_reason}",
        metadata={"reason": rejection_reason},
        ip_address=ip_address,
    )
    logger.info("Dispute letter rejected", letter_id=str(letter.id), reason=rejection_reason)
    return letter


# ---------------------------------------------------------------------------
# 4. File dispute to bureau
# ---------------------------------------------------------------------------

async def file_dispute_to_bureau(
    db: Session,
    *,
    dispute_case: DisputeCase,
    letter: DisputeLetter,
    actor_user_id: Optional[uuid.UUID] = None,
    ip_address: Optional[str] = None,
) -> dict:
    """
    File approved dispute letter to the specified bureau.

    In production: calls bureau API or generates certified mail package.
    Currently implements simulation with tracking number generation.

    Returns: {"tracking_number": str, "filed_at": datetime}
    """
    if letter.status != LetterStatus.APPROVED:
        raise ValueError(f"Letter must be APPROVED before filing (current: {letter.status})")

    if dispute_case.status not in (DisputeStatus.APPROVED, DisputeStatus.PENDING_FILING):
        raise ValueError(f"Case must be APPROVED before filing (current: {dispute_case.status})")

    # Generate tracking number
    tracking_number = f"TLS-{dispute_case.bureau.upper()[:3]}-{uuid.uuid4().hex[:8].upper()}"
    filed_at = datetime.now(timezone.utc)
    expected_response = filed_at + timedelta(days=30)

    # Update case
    dispute_case.status = DisputeStatus.FILED
    dispute_case.filed_date = filed_at
    dispute_case.expected_response_date = expected_response

    # Update letter
    letter.status = LetterStatus.FILED

    _log_audit(
        db=db,
        action=AuditAction.DISPUTE_FILED,
        subject_type="dispute_case",
        subject_id=dispute_case.id,
        client_id=dispute_case.client_id,
        actor_user_id=actor_user_id,
        actor_type="system",
        description=f"Dispute filed to {dispute_case.bureau}. Tracking: {tracking_number}",
        metadata={
            "bureau": dispute_case.bureau,
            "tracking_number": tracking_number,
            "filed_at": filed_at.isoformat(),
            "expected_response": expected_response.isoformat(),
            "letter_id": str(letter.id),
        },
        ip_address=ip_address,
    )

    logger.info(
        "Dispute filed",
        case_id=str(dispute_case.id),
        bureau=dispute_case.bureau,
        tracking=tracking_number,
    )

    return {
        "tracking_number": tracking_number,
        "filed_at": filed_at,
        "expected_response_date": expected_response,
    }


# ---------------------------------------------------------------------------
# 5. Record bureau response
# ---------------------------------------------------------------------------

def record_bureau_response(
    db: Session,
    *,
    dispute_case: DisputeCase,
    response_type: BureauResponseType,
    response_content: Optional[str] = None,
    response_url: Optional[str] = None,
    score_impact: Optional[int] = None,
    actor_user_id: Optional[uuid.UUID] = None,
    ip_address: Optional[str] = None,
) -> BureauResponse:
    """
    Record a bureau response and update case status accordingly.
    """
    received_at = datetime.now(timezone.utc)

    response = BureauResponse(
        dispute_id=dispute_case.id,
        received_date=received_at,
        response_type=response_type,
        response_content=response_content,
        response_url=response_url,
        score_impact=score_impact,
    )
    db.add(response)

    # Update case
    dispute_case.response_received_date = received_at
    dispute_case.status = DisputeStatus.RESPONDED

    if response_type in (BureauResponseType.REMOVED, BureauResponseType.DELETED):
        dispute_case.outcome = response_type
        dispute_case.outcome_date = received_at
        dispute_case.score_impact_points = score_impact
        dispute_case.status = DisputeStatus.RESOLVED

        # Update the tradeline if linked
        if dispute_case.tradeline_id:
            tradeline = db.query(Tradeline).get(dispute_case.tradeline_id)
            if tradeline:
                tradeline.status = "disputed"  # Mark as removed/disputed

    elif response_type == BureauResponseType.VERIFIED:
        dispute_case.outcome = response_type
        dispute_case.outcome_date = received_at
        dispute_case.status = DisputeStatus.RESOLVED

    elif response_type == BureauResponseType.REINVESTIGATION:
        # Bureau needs more time — keep as RESPONDING, extend timeline
        dispute_case.expected_response_date = received_at + timedelta(days=15)

    db.flush()

    _log_audit(
        db=db,
        action=AuditAction.DISPUTE_RESPONSE_RECEIVED,
        subject_type="dispute_case",
        subject_id=dispute_case.id,
        client_id=dispute_case.client_id,
        actor_user_id=actor_user_id,
        actor_type="system",
        description=f"Bureau response received: {response_type.value}",
        metadata={
            "response_type": response_type.value,
            "score_impact": score_impact,
            "response_id": str(response.id),
        },
        ip_address=ip_address,
    )

    if dispute_case.status == DisputeStatus.RESOLVED:
        _log_audit(
            db=db,
            action=AuditAction.DISPUTE_RESOLVED,
            subject_type="dispute_case",
            subject_id=dispute_case.id,
            client_id=dispute_case.client_id,
            actor_type="system",
            description=f"Dispute resolved: {response_type.value}",
            metadata={"outcome": response_type.value, "score_impact": score_impact},
        )

    logger.info(
        "Bureau response recorded",
        case_id=str(dispute_case.id),
        response_type=response_type.value,
        resolved=dispute_case.status == DisputeStatus.RESOLVED,
    )
    return response


# ---------------------------------------------------------------------------
# 6. Get dispute status summary
# ---------------------------------------------------------------------------

def get_dispute_status_summary(
    db: Session,
    *,
    dispute_case: DisputeCase,
) -> dict:
    """Build a complete status summary dict for a dispute case."""
    latest_letter = (
        db.query(DisputeLetter)
        .filter(DisputeLetter.dispute_id == dispute_case.id)
        .order_by(DisputeLetter.letter_version.desc())
        .first()
    )

    latest_response = (
        db.query(BureauResponse)
        .filter(BureauResponse.dispute_id == dispute_case.id)
        .order_by(BureauResponse.received_date.desc())
        .first()
    )

    days_investigating = None
    days_remaining = None
    overdue = False

    if dispute_case.filed_date:
        now = datetime.now(timezone.utc)
        days_investigating = (now - dispute_case.filed_date).days
        if dispute_case.expected_response_date:
            days_remaining = (dispute_case.expected_response_date - now).days
            overdue = days_remaining < 0

    return {
        "dispute_id": str(dispute_case.id),
        "client_id": str(dispute_case.client_id),
        "bureau": dispute_case.bureau,
        "dispute_reason": dispute_case.dispute_reason.value,
        "creditor_name": dispute_case.creditor_name,
        "status": dispute_case.status.value,
        "filed_date": dispute_case.filed_date.isoformat() if dispute_case.filed_date else None,
        "expected_response_date": (
            dispute_case.expected_response_date.isoformat()
            if dispute_case.expected_response_date
            else None
        ),
        "days_investigating": days_investigating,
        "days_remaining": days_remaining,
        "overdue": overdue,
        "outcome": dispute_case.outcome.value if dispute_case.outcome else None,
        "outcome_date": dispute_case.outcome_date.isoformat() if dispute_case.outcome_date else None,
        "score_impact": dispute_case.score_impact_points,
        "letter": {
            "id": str(latest_letter.id),
            "version": latest_letter.letter_version,
            "status": latest_letter.status.value,
            "compliance_status": latest_letter.compliance_status,
            "compliance_flags": latest_letter.compliance_flags,
            "approved_by": str(latest_letter.approved_by_admin_id) if latest_letter.approved_by_admin_id else None,
            "approval_date": latest_letter.approval_date.isoformat() if latest_letter.approval_date else None,
        } if latest_letter else None,
        "latest_response": {
            "type": latest_response.response_type.value,
            "received_date": latest_response.received_date.isoformat(),
            "score_impact": latest_response.score_impact,
        } if latest_response else None,
    }


# ---------------------------------------------------------------------------
# 7. Get overdue disputes (for background monitor)
# ---------------------------------------------------------------------------

def get_overdue_disputes(db: Session) -> list[DisputeCase]:
    """Return disputes that have exceeded their expected response date."""
    now = datetime.now(timezone.utc)
    return (
        db.query(DisputeCase)
        .filter(
            DisputeCase.status == DisputeStatus.FILED,
            DisputeCase.expected_response_date < now,
        )
        .all()
    )


def get_disputes_needing_check(db: Session, days: int = 7) -> list[DisputeCase]:
    """Return filed disputes that haven't been checked in `days` days."""
    from sqlalchemy import and_, or_

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return (
        db.query(DisputeCase)
        .filter(
            DisputeCase.status.in_([DisputeStatus.FILED, DisputeStatus.INVESTIGATING]),
            DisputeCase.filed_date.isnot(None),
        )
        .all()
    )
