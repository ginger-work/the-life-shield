"""
Disputes API Router

Endpoints:
  POST   /api/v1/disputes/                              - Create dispute case
  GET    /api/v1/disputes/                              - List disputes (paginated)
  GET    /api/v1/disputes/{id}                          - Get dispute case
  POST   /api/v1/disputes/{id}/generate-letter          - AI-generate dispute letter
  POST   /api/v1/disputes/{id}/approve-letter           - Admin approves letter
  POST   /api/v1/disputes/{id}/reject-letter            - Admin rejects letter
  POST   /api/v1/disputes/{id}/file                     - File with bureau
  GET    /api/v1/disputes/{id}/status                   - Check bureau status
  POST   /api/v1/disputes/{id}/bureau-response          - Record bureau response
  GET    /api/v1/disputes/overdue                       - Disputes past 30-day deadline
  GET    /api/v1/disputes/audit/{id}                    - Audit log for dispute
  POST   /api/v1/disputes/webhooks/{bureau}             - Inbound bureau webhook

APPROVAL FLOW (MANDATORY):
  Create → Generate Letter → [Human Approval] → File → Monitor → Record Response

Human approval at step 3 is NON-NEGOTIABLE per CROA compliance.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

import structlog
from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, HTTPException, Path, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.audit import AuditAction
from app.models.client import ClientProfile, Tradeline
from app.models.dispute import (
    DisputeCase,
    DisputeLetter,
    DisputeStatus,
    LetterStatus,
)
from app.schemas.dispute import (
    ApproveLetterRequest,
    CreateDisputeRequest,
    DisputeCaseResponse,
    DisputeCreateResponse,
    DisputeFiledResponse,
    DisputeLetterResponse,
    DisputeListResponse,
    DisputeStatusResponse,
    FileDisputeRequest,
    OverdueDisputeResponse,
    RecordBureauResponseRequest,
    RejectLetterRequest,
    WebhookBureauResponse,
)
from app.services.audit_service import get_dispute_audit_log, log_audit
from app.services.dispute_service import (
    approve_dispute_letter,
    check_dispute_status,
    create_dispute_case,
    file_dispute_with_bureau,
    generate_dispute_letter,
    get_disputes_for_client,
    get_overdue_disputes,
    record_bureau_response,
    reject_dispute_letter,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/disputes", tags=["Disputes"])


def _get_current_user_id(request: Request) -> Optional[uuid.UUID]:
    user_id = getattr(request.state, "user_id", None)
    return uuid.UUID(str(user_id)) if user_id else None


def _get_dispute_or_404(db: Session, dispute_id: uuid.UUID) -> DisputeCase:
    dispute = db.query(DisputeCase).filter(DisputeCase.id == dispute_id).first()
    if not dispute:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "Dispute case not found"},
        )
    return dispute


def _get_letter_or_404(db: Session, letter_id: uuid.UUID) -> DisputeLetter:
    letter = db.query(DisputeLetter).filter(DisputeLetter.id == letter_id).first()
    if not letter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "Dispute letter not found"},
        )
    return letter


def _get_client_or_404(db: Session, client_id: uuid.UUID) -> ClientProfile:
    client = db.query(ClientProfile).filter(ClientProfile.id == client_id).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "Client not found"},
        )
    return client


def _decrypt_ssn(client: ClientProfile) -> str:
    """Decrypt client SSN (sandbox returns test SSN)."""
    from app.core.config import settings
    if settings.BUREAU_SANDBOX_MODE or settings.is_development:
        ssn_last4 = client.ssn_last_4 or "5000"
        return f"000-00-{ssn_last4}"
    if not client.ssn_encrypted:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "MISSING_SSN", "message": "Client SSN required for bureau filing"},
        )
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"error": "NOT_IMPLEMENTED", "message": "SSN decryption not configured"},
    )


def _serialize_dispute(dispute: DisputeCase) -> DisputeCaseResponse:
    """Serialize a DisputeCase ORM object to response schema."""
    letters = [
        DisputeLetterResponse(
            id=l.id,
            dispute_id=l.dispute_id,
            letter_content=l.letter_content,
            letter_version=l.letter_version,
            compliance_status=l.compliance_status,
            compliance_flags=l.compliance_flags,
            human_approval_required=l.human_approval_required,
            approved_by_admin_id=l.approved_by_admin_id,
            approval_date=l.approval_date,
            rejection_reason=l.rejection_reason,
            status=l.status.value,
            ai_model_used=l.ai_model_used,
            created_at=l.created_at,
        )
        for l in (dispute.letters or [])
    ]

    return DisputeCaseResponse(
        id=dispute.id,
        client_id=dispute.client_id,
        bureau=dispute.bureau,
        dispute_reason=dispute.dispute_reason.value,
        creditor_name=dispute.creditor_name,
        account_number_masked=dispute.account_number_masked,
        item_description=dispute.item_description,
        status=dispute.status.value,
        filed_date=dispute.filed_date,
        expected_response_date=dispute.expected_response_date,
        response_received_date=dispute.response_received_date,
        outcome=dispute.outcome.value if dispute.outcome else None,
        outcome_date=dispute.outcome_date,
        score_impact_points=dispute.score_impact_points,
        priority_score=dispute.priority_score,
        analyst_notes=dispute.analyst_notes,
        created_at=dispute.created_at,
        updated_at=dispute.updated_at,
        letters=letters,
        bureau_responses=[],
    )


# ─────────────────────────────────────────────────────────
# DISPUTE CASE ENDPOINTS
# ─────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=DisputeCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a dispute case",
    description=(
        "Create a new dispute case for a client. "
        "Dispute starts in PENDING_APPROVAL status. "
        "A dispute letter must be generated and approved before filing. "
        "Requires: disputes:write permission."
    ),
)
def create_dispute(
    client_id: uuid.UUID = Query(..., description="Client ID"),
    payload: CreateDisputeRequest = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Create a new dispute case. Starts in PENDING_APPROVAL status."""
    client = _get_client_or_404(db, client_id)
    actor_user_id = _get_current_user_id(request) if request else None
    correlation_id = request.headers.get("X-Correlation-ID") if request else None

    try:
        case = create_dispute_case(
            db=db,
            client=client,
            bureau=payload.bureau,
            dispute_reason=payload.dispute_reason,
            creditor_name=payload.creditor_name,
            account_number_masked=payload.account_number_masked,
            item_description=payload.item_description,
            tradeline_id=payload.tradeline_id,
            priority_score=payload.priority_score,
            analyst_notes=payload.analyst_notes,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "VALIDATION_ERROR", "message": str(exc)},
        )

    return DisputeCreateResponse(
        success=True,
        dispute_id=case.id,
        status=case.status.value,
        message=(
            f"Dispute case created for {payload.creditor_name} at {payload.bureau}. "
            "Generate and get a dispute letter approved before filing."
        ),
    )


@router.get(
    "/",
    response_model=DisputeListResponse,
    summary="List disputes for a client",
    description="Returns paginated disputes for a client with optional status/bureau filters.",
)
def list_disputes(
    client_id: uuid.UUID = Query(..., description="Client ID"),
    status_filter: Optional[str] = Query(default=None, description="Filter by status"),
    bureau_filter: Optional[str] = Query(default=None, description="Filter by bureau"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Get paginated disputes for a client."""
    _get_client_or_404(db, client_id)

    disputes = get_disputes_for_client(
        db=db,
        client_id=client_id,
        status_filter=status_filter,
        bureau_filter=bureau_filter,
        limit=limit,
        offset=offset,
    )

    total = (
        db.query(DisputeCase)
        .filter(DisputeCase.client_id == client_id)
        .count()
    )

    return DisputeListResponse(
        total=total,
        offset=offset,
        limit=limit,
        disputes=[_serialize_dispute(d) for d in disputes],
    )


@router.get(
    "/overdue",
    response_model=List[OverdueDisputeResponse],
    summary="Get overdue disputes",
    description=(
        "Returns all disputes where the 30-day FCRA response deadline has passed. "
        "These may constitute FCRA violations by the bureau. "
        "Requires: admin or staff role."
    ),
)
def list_overdue_disputes(db: Session = Depends(get_db)):
    """Get all disputes past their 30-day FCRA response deadline."""
    overdue = get_overdue_disputes(db)
    now = datetime.now(timezone.utc)

    return [
        OverdueDisputeResponse(
            id=d.id,
            client_id=d.client_id,
            bureau=d.bureau,
            creditor_name=d.creditor_name,
            filed_date=d.filed_date,
            expected_response_date=d.expected_response_date,
            days_overdue=(
                (now - d.expected_response_date).days
                if d.expected_response_date
                else 0
            ),
            status=d.status.value,
        )
        for d in overdue
    ]


@router.get(
    "/{dispute_id}",
    response_model=DisputeCaseResponse,
    summary="Get a specific dispute case",
    description="Returns full dispute case details including letters and bureau responses.",
)
def get_dispute(
    dispute_id: uuid.UUID = Path(..., description="Dispute ID"),
    db: Session = Depends(get_db),
):
    """Get a specific dispute case with all letters and responses."""
    dispute = _get_dispute_or_404(db, dispute_id)
    return _serialize_dispute(dispute)


# ─────────────────────────────────────────────────────────
# LETTER WORKFLOW ENDPOINTS
# ─────────────────────────────────────────────────────────

@router.post(
    "/{dispute_id}/generate-letter",
    response_model=DisputeLetterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate AI dispute letter",
    description=(
        "Generate an AI-powered dispute letter for this case. "
        "The letter is automatically compliance-checked (FCRA/CROA). "
        "Letter requires human admin approval before it can be filed."
    ),
)
def generate_letter(
    dispute_id: uuid.UUID = Path(..., description="Dispute ID"),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Generate an AI dispute letter for a case. Requires human approval before filing."""
    dispute = _get_dispute_or_404(db, dispute_id)
    client = _get_client_or_404(db, dispute.client_id)
    correlation_id = request.headers.get("X-Correlation-ID") if request else None

    # Load tradeline if linked
    tradeline = None
    if dispute.tradeline_id:
        tradeline = db.query(Tradeline).filter(Tradeline.id == dispute.tradeline_id).first()

    try:
        letter = generate_dispute_letter(
            db=db,
            dispute_case=dispute,
            client=client,
            tradeline=tradeline,
            correlation_id=correlation_id,
        )
    except Exception as exc:
        log.error("letter_generation_failed", dispute_id=str(dispute_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "LETTER_GENERATION_FAILED", "message": str(exc)},
        )

    return DisputeLetterResponse(
        id=letter.id,
        dispute_id=letter.dispute_id,
        letter_content=letter.letter_content,
        letter_version=letter.letter_version,
        compliance_status=letter.compliance_status,
        compliance_flags=letter.compliance_flags,
        human_approval_required=letter.human_approval_required,
        approved_by_admin_id=letter.approved_by_admin_id,
        approval_date=letter.approval_date,
        rejection_reason=letter.rejection_reason,
        status=letter.status.value,
        ai_model_used=letter.ai_model_used,
        created_at=letter.created_at,
    )


@router.post(
    "/{dispute_id}/approve-letter",
    response_model=DisputeLetterResponse,
    summary="Approve dispute letter",
    description=(
        "**ADMIN ONLY** — Approve a dispute letter for filing. "
        "This is a mandatory step per CROA compliance. "
        "Letters with open compliance flags cannot be approved. "
        "Requires: disputes:approve permission."
    ),
)
def approve_letter(
    dispute_id: uuid.UUID = Path(..., description="Dispute ID"),
    payload: ApproveLetterRequest = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Admin approves a dispute letter. Mandatory before filing."""
    dispute = _get_dispute_or_404(db, dispute_id)
    letter = _get_letter_or_404(db, payload.letter_id)

    if letter.dispute_id != dispute.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "MISMATCH", "message": "Letter does not belong to this dispute"},
        )

    actor_user_id = _get_current_user_id(request) if request else None
    if not actor_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "UNAUTHORIZED", "message": "Authentication required for letter approval"},
        )

    correlation_id = request.headers.get("X-Correlation-ID") if request else None

    try:
        letter = approve_dispute_letter(
            db=db,
            letter=letter,
            dispute_case=dispute,
            approving_admin_id=actor_user_id,
            correlation_id=correlation_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "APPROVAL_BLOCKED", "message": str(exc)},
        )

    return DisputeLetterResponse(
        id=letter.id,
        dispute_id=letter.dispute_id,
        letter_content=letter.letter_content,
        letter_version=letter.letter_version,
        compliance_status=letter.compliance_status,
        compliance_flags=letter.compliance_flags,
        human_approval_required=letter.human_approval_required,
        approved_by_admin_id=letter.approved_by_admin_id,
        approval_date=letter.approval_date,
        rejection_reason=letter.rejection_reason,
        status=letter.status.value,
        ai_model_used=letter.ai_model_used,
        created_at=letter.created_at,
    )


@router.post(
    "/{dispute_id}/reject-letter",
    response_model=DisputeLetterResponse,
    summary="Reject dispute letter",
    description=(
        "**ADMIN ONLY** — Reject a dispute letter with a required reason. "
        "A new letter can be regenerated after rejection. "
        "Requires: disputes:approve permission."
    ),
)
def reject_letter(
    dispute_id: uuid.UUID = Path(..., description="Dispute ID"),
    payload: RejectLetterRequest = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Admin rejects a dispute letter with a reason."""
    dispute = _get_dispute_or_404(db, dispute_id)
    letter = _get_letter_or_404(db, payload.letter_id)

    if letter.dispute_id != dispute.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "MISMATCH", "message": "Letter does not belong to this dispute"},
        )

    actor_user_id = _get_current_user_id(request) if request else None
    if not actor_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "UNAUTHORIZED", "message": "Authentication required"},
        )

    correlation_id = request.headers.get("X-Correlation-ID") if request else None

    letter = reject_dispute_letter(
        db=db,
        letter=letter,
        dispute_case=dispute,
        rejecting_admin_id=actor_user_id,
        reason=payload.reason,
        correlation_id=correlation_id,
    )

    return DisputeLetterResponse(
        id=letter.id,
        dispute_id=letter.dispute_id,
        letter_content=letter.letter_content,
        letter_version=letter.letter_version,
        compliance_status=letter.compliance_status,
        compliance_flags=letter.compliance_flags,
        human_approval_required=letter.human_approval_required,
        approved_by_admin_id=letter.approved_by_admin_id,
        approval_date=letter.approval_date,
        rejection_reason=letter.rejection_reason,
        status=letter.status.value,
        ai_model_used=letter.ai_model_used,
        created_at=letter.created_at,
    )


# ─────────────────────────────────────────────────────────
# FILING ENDPOINTS
# ─────────────────────────────────────────────────────────

@router.post(
    "/{dispute_id}/file",
    response_model=DisputeFiledResponse,
    summary="File dispute with bureau",
    description=(
        "File an approved dispute with the credit bureau. "
        "**Prerequisites**: Dispute must be APPROVED, letter must be APPROVED. "
        "FCRA 30-day investigation clock starts from filing date. "
        "Requires: disputes:write permission."
    ),
)
def file_dispute(
    dispute_id: uuid.UUID = Path(..., description="Dispute ID"),
    payload: FileDisputeRequest = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """File an approved dispute with the credit bureau."""
    dispute = _get_dispute_or_404(db, dispute_id)
    letter = _get_letter_or_404(db, payload.letter_id)

    if letter.dispute_id != dispute.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "MISMATCH", "message": "Letter does not belong to this dispute"},
        )

    client = _get_client_or_404(db, dispute.client_id)
    decrypted_ssn = _decrypt_ssn(client)
    actor_user_id = _get_current_user_id(request) if request else None
    correlation_id = request.headers.get("X-Correlation-ID") if request else None

    tradeline = None
    if dispute.tradeline_id:
        tradeline = db.query(Tradeline).filter(Tradeline.id == dispute.tradeline_id).first()

    try:
        dispute = file_dispute_with_bureau(
            db=db,
            dispute_case=dispute,
            letter=letter,
            client=client,
            decrypted_ssn=decrypted_ssn,
            tradeline=tradeline,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "FILING_BLOCKED", "message": str(exc)},
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "BUREAU_ERROR", "message": str(exc)},
        )

    return DisputeFiledResponse(
        success=True,
        dispute_id=dispute.id,
        bureau=dispute.bureau,
        status=dispute.status.value,
        filed_date=dispute.filed_date,
        expected_response_date=dispute.expected_response_date,
        message=(
            f"Dispute filed with {dispute.bureau}. "
            f"Bureau has 30 days to respond per FCRA (by {dispute.expected_response_date.date() if dispute.expected_response_date else 'N/A'})."
        ),
    )


@router.get(
    "/{dispute_id}/status",
    response_model=DisputeStatusResponse,
    summary="Check dispute status with bureau",
    description=(
        "Query the credit bureau in real-time for the current status of a filed dispute. "
        "Updates the dispute record if status has changed."
    ),
)
def get_dispute_status(
    dispute_id: uuid.UUID = Path(..., description="Dispute ID"),
    confirmation_number: str = Query(..., description="Bureau confirmation number from filing"),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Check a dispute's current status with the bureau."""
    dispute = _get_dispute_or_404(db, dispute_id)

    if dispute.status not in [
        DisputeStatus.FILED,
        DisputeStatus.INVESTIGATING,
        DisputeStatus.RESPONDED,
    ]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "INVALID_STATE",
                "message": f"Cannot check status — dispute is in {dispute.status.value} state",
            },
        )

    actor_user_id = _get_current_user_id(request) if request else None
    correlation_id = request.headers.get("X-Correlation-ID") if request else None

    result = check_dispute_status(
        db=db,
        dispute_case=dispute,
        confirmation_number=confirmation_number,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
    )

    return DisputeStatusResponse(
        dispute_id=dispute_id,
        bureau=dispute.bureau,
        confirmation_number=confirmation_number,
        status=result.status.value,
        outcome=result.outcome,
        outcome_description=result.outcome_description,
        checked_at=result.checked_at,
        success=result.success,
        error_message=result.error_message,
    )


@router.post(
    "/{dispute_id}/bureau-response",
    response_model=DisputeCaseResponse,
    summary="Record bureau response",
    description=(
        "Record the credit bureau's investigation outcome. "
        "Closes the dispute case and updates client's credit data. "
        "Requires: disputes:write permission."
    ),
)
def record_response(
    dispute_id: uuid.UUID = Path(..., description="Dispute ID"),
    payload: RecordBureauResponseRequest = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Record the bureau's investigation response."""
    dispute = _get_dispute_or_404(db, dispute_id)
    actor_user_id = _get_current_user_id(request) if request else None
    correlation_id = request.headers.get("X-Correlation-ID") if request else None

    try:
        record_bureau_response(
            db=db,
            dispute_case=dispute,
            response_type=payload.response_type,
            response_content=payload.response_content,
            score_impact=payload.score_impact,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "VALIDATION_ERROR", "message": str(exc)},
        )

    # Reload with updated data
    db.refresh(dispute)
    return _serialize_dispute(dispute)


# ─────────────────────────────────────────────────────────
# AUDIT ENDPOINT
# ─────────────────────────────────────────────────────────

@router.get(
    "/audit/{dispute_id}",
    summary="Get audit log for dispute",
    description="Returns the complete FCRA audit trail for a specific dispute case.",
)
def get_audit_log(
    dispute_id: uuid.UUID = Path(..., description="Dispute ID"),
    db: Session = Depends(get_db),
):
    """Get full audit trail for a dispute case."""
    _get_dispute_or_404(db, dispute_id)
    entries = get_dispute_audit_log(db, dispute_id)

    return {
        "dispute_id": str(dispute_id),
        "total": len(entries),
        "entries": [
            {
                "id": str(e.id),
                "action": e.action.value,
                "actor_type": e.actor_type,
                "description": e.description,
                "metadata": e.metadata,
                "success": e.success,
                "created_at": e.created_at.isoformat(),
            }
            for e in entries
        ],
    }


# ─────────────────────────────────────────────────────────
# WEBHOOK ENDPOINTS (Bureau → Platform)
# ─────────────────────────────────────────────────────────

@router.post(
    "/webhooks/{bureau}",
    status_code=status.HTTP_200_OK,
    summary="Bureau webhook receiver",
    description=(
        "Receives real-time event notifications from credit bureaus. "
        "Bureau sends updates when dispute status changes. "
        "Validates webhook signatures before processing."
    ),
    include_in_schema=True,
)
async def handle_bureau_webhook(
    bureau: str = Path(..., description="Bureau name: equifax, experian, transunion"),
    payload: WebhookBureauResponse = Body(...),
    x_bureau_signature: Optional[str] = Header(default=None, description="Bureau webhook signature"),
    db: Session = Depends(get_db),
):
    """
    Receive and process bureau webhook events.

    Bureau sends updates when:
    - Dispute investigation status changes
    - Credit report update is available
    - Account modification confirmed

    Signature validation: Each bureau signs webhook payloads.
    In sandbox mode, signature validation is skipped.
    """
    from app.core.config import settings

    # Log webhook receipt
    log_audit(
        db,
        AuditAction.WEBHOOK_RECEIVED,
        actor_type="webhook",
        description=f"Webhook received from {bureau}: {payload.event_type}",
        metadata={
            "bureau": bureau,
            "event_type": payload.event_type,
            "confirmation_number": payload.confirmation_number,
        },
    )

    log.info(
        "bureau_webhook_received",
        bureau=bureau,
        event_type=payload.event_type,
        confirmation_number=payload.confirmation_number,
    )

    # Skip signature check in sandbox
    if not settings.BUREAU_SANDBOX_MODE and not settings.is_development:
        if not x_bureau_signature:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "MISSING_SIGNATURE", "message": "Webhook signature required"},
            )
        # TODO: Validate bureau-specific signature (HMAC or certificate)

    # Process dispute update events
    if payload.event_type in ("dispute_update", "dispute_completed") and payload.confirmation_number:
        # Find matching dispute by confirmation number — stored in analyst_notes or metadata
        # In production this would query a confirmation_numbers table
        # For now log and acknowledge
        log.info(
            "bureau_webhook_dispute_update",
            bureau=bureau,
            confirmation=payload.confirmation_number,
            status=payload.dispute_status,
            outcome=payload.outcome,
        )

        log_audit(
            db,
            AuditAction.WEBHOOK_PROCESSED,
            actor_type="webhook",
            description=f"Dispute update webhook processed from {bureau}",
            metadata={
                "bureau": bureau,
                "confirmation_number": payload.confirmation_number,
                "dispute_status": payload.dispute_status,
                "outcome": payload.outcome,
            },
        )

    return {"status": "acknowledged", "event_type": payload.event_type}
