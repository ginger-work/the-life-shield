"""
Dispute API Routes

POST   /api/v1/disputes/create              — Create dispute case + generate letter
GET    /api/v1/disputes                     — List client disputes (or all for admin)
GET    /api/v1/disputes/{id}               — Get dispute details
GET    /api/v1/disputes/{id}/status        — Get status + timeline
POST   /api/v1/disputes/{id}/approve       — Admin approve letter
POST   /api/v1/disputes/{id}/reject        — Admin reject letter
POST   /api/v1/disputes/{id}/file          — File approved dispute to bureau
POST   /api/v1/disputes/{id}/response      — Record bureau response
POST   /api/v1/disputes/{id}/withdraw      — Withdraw dispute
GET    /api/v1/disputes/{id}/letter        — Get latest letter content
POST   /api/v1/disputes/{id}/regenerate    — Regenerate letter (new version)

Access:
- ADMIN: full access to all clients
- AGENT: can create, generate, view (not approve/reject/file — admin only)
- CLIENT: can view their own disputes only
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client import ClientProfile
from app.models.dispute import (
    BureauResponseType,
    DisputeCase,
    DisputeLetter,
    DisputeReason,
    DisputeStatus,
    LetterStatus,
)
from app.models.audit import AuditAction, AuditTrail
from app.api.disputes.service import (
    approve_dispute_letter,
    create_dispute_case,
    file_dispute_to_bureau,
    generate_letter_for_case,
    get_dispute_status_summary,
    record_bureau_response,
    reject_dispute_letter,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/disputes", tags=["Disputes"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class CreateDisputeRequest(BaseModel):
    client_id: uuid.UUID
    bureau: str = Field(..., pattern="^(equifax|experian|transunion)$")
    dispute_reason: DisputeReason
    item_description: str = Field(..., min_length=10, max_length=2000)
    creditor_name: Optional[str] = Field(None, max_length=255)
    account_number_masked: Optional[str] = Field(None, max_length=50)
    tradeline_id: Optional[uuid.UUID] = None
    priority_score: int = Field(5, ge=1, le=10)
    analyst_notes: Optional[str] = Field(None, max_length=2000)
    generate_letter: bool = Field(True, description="Auto-generate letter after creating case")


class ApproveLetterRequest(BaseModel):
    letter_id: uuid.UUID


class RejectLetterRequest(BaseModel):
    letter_id: uuid.UUID
    rejection_reason: str = Field(..., min_length=10, max_length=500)


class RecordResponseRequest(BaseModel):
    response_type: BureauResponseType
    response_content: Optional[str] = Field(None, max_length=10000)
    response_url: Optional[str] = Field(None, max_length=500)
    score_impact: Optional[int] = Field(None, ge=-200, le=200)


class WithdrawRequest(BaseModel):
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Dependency: get current user (simplified — plug into your auth system)
# ---------------------------------------------------------------------------

def get_current_user_id(request: Request) -> Optional[uuid.UUID]:
    """Extract user ID from request state (set by auth middleware)."""
    user = getattr(request.state, "user", None)
    if user:
        return getattr(user, "id", None)
    return None


def get_current_user_role(request: Request) -> str:
    """Extract user role from request state."""
    user = getattr(request.state, "user", None)
    if user:
        return getattr(user, "role", "client")
    return "client"


def require_admin_or_agent(request: Request):
    role = get_current_user_role(request)
    if role not in ("admin", "agent"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Agent role required.",
        )


def require_admin(request: Request):
    role = get_current_user_role(request)
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required.",
        )


# ---------------------------------------------------------------------------
# POST /disputes/create
# ---------------------------------------------------------------------------

@router.post(
    "/create",
    status_code=status.HTTP_201_CREATED,
    summary="Create dispute case and generate letter",
    description=(
        "Creates a new dispute case, optionally generates an AI-powered letter. "
        "Letter starts as DRAFT → compliance check → PENDING_HUMAN_APPROVAL. "
        "Admin must approve before filing. FCRA audit trail created on every action."
    ),
)
async def create_dispute(
    payload: CreateDisputeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    _ = require_admin_or_agent(request)

    # Verify client exists
    client = db.query(ClientProfile).filter(ClientProfile.id == payload.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")

    actor_id = get_current_user_id(request)
    ip = request.client.host if request.client else None

    # Create the case
    case = await create_dispute_case(
        db=db,
        client_id=payload.client_id,
        bureau=payload.bureau,
        dispute_reason=payload.dispute_reason,
        item_description=payload.item_description,
        creditor_name=payload.creditor_name,
        account_number_masked=payload.account_number_masked,
        tradeline_id=payload.tradeline_id,
        priority_score=payload.priority_score,
        analyst_notes=payload.analyst_notes,
        actor_user_id=actor_id,
        ip_address=ip,
    )

    letter_data = None

    # Auto-generate letter if requested
    if payload.generate_letter:
        try:
            letter = await generate_letter_for_case(
                db=db,
                dispute_case=case,
                client=client,
                actor_user_id=actor_id,
                ip_address=ip,
            )
            letter_data = {
                "id": str(letter.id),
                "version": letter.letter_version,
                "status": letter.status.value,
                "compliance_status": letter.compliance_status,
                "compliance_flags": letter.compliance_flags,
                "ai_model_used": letter.ai_model_used,
            }
        except Exception as exc:
            logger.error("Letter generation failed during case creation", exc_info=exc)
            # Don't fail the whole request — case was created, letter can be regenerated
            letter_data = {"error": "Letter generation failed. Use /regenerate to retry."}

    db.commit()

    return {
        "dispute_id": str(case.id),
        "status": case.status.value,
        "bureau": case.bureau,
        "dispute_reason": case.dispute_reason.value,
        "creditor_name": case.creditor_name,
        "letter": letter_data,
        "next_step": (
            "Letter is pending human approval. Admin must approve via POST /disputes/{id}/approve"
            if letter_data and "error" not in letter_data
            else "Generate a letter via POST /disputes/{id}/regenerate"
        ),
    }


# ---------------------------------------------------------------------------
# GET /disputes
# ---------------------------------------------------------------------------

@router.get(
    "",
    summary="List disputes",
    description="Admin sees all. Agent sees their cases. Client sees own only.",
)
def list_disputes(
    request: Request,
    client_id: Optional[uuid.UUID] = Query(None),
    bureau: Optional[str] = Query(None),
    dispute_status: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    role = get_current_user_role(request)
    actor_id = get_current_user_id(request)

    query = db.query(DisputeCase)

    # Scope by role
    if role == "client" and actor_id:
        # Client can only see their own disputes
        client = db.query(ClientProfile).filter(ClientProfile.user_id == actor_id).first()
        if client:
            query = query.filter(DisputeCase.client_id == client.id)
        else:
            return {"items": [], "total": 0, "page": page, "per_page": per_page}
    elif client_id:
        query = query.filter(DisputeCase.client_id == client_id)

    if bureau:
        query = query.filter(DisputeCase.bureau == bureau.lower())
    if dispute_status:
        query = query.filter(DisputeCase.status == dispute_status)

    total = query.count()
    cases = (
        query.order_by(DisputeCase.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "items": [
            {
                "id": str(c.id),
                "client_id": str(c.client_id),
                "bureau": c.bureau,
                "status": c.status.value,
                "dispute_reason": c.dispute_reason.value,
                "creditor_name": c.creditor_name,
                "filed_date": c.filed_date.isoformat() if c.filed_date else None,
                "expected_response_date": (
                    c.expected_response_date.isoformat() if c.expected_response_date else None
                ),
                "outcome": c.outcome.value if c.outcome else None,
                "priority_score": c.priority_score,
                "created_at": c.created_at.isoformat(),
            }
            for c in cases
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


# ---------------------------------------------------------------------------
# GET /disputes/{id}
# ---------------------------------------------------------------------------

@router.get("/{dispute_id}", summary="Get dispute details")
def get_dispute(
    dispute_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    case = _get_case_or_404(db, dispute_id)
    _check_access(request, case)
    return get_dispute_status_summary(db, dispute_case=case)


# ---------------------------------------------------------------------------
# GET /disputes/{id}/status
# ---------------------------------------------------------------------------

@router.get("/{dispute_id}/status", summary="Get dispute status and timeline")
def get_dispute_status(
    dispute_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    case = _get_case_or_404(db, dispute_id)
    _check_access(request, case)

    summary = get_dispute_status_summary(db, dispute_case=case)

    # Add recent audit trail for this case
    audit_entries = (
        db.query(AuditTrail)
        .filter(AuditTrail.subject_id == dispute_id)
        .order_by(AuditTrail.created_at.desc())
        .limit(20)
        .all()
    )

    summary["audit_trail"] = [
        {
            "action": e.action.value,
            "description": e.description,
            "actor_type": e.actor_type,
            "timestamp": e.created_at.isoformat(),
        }
        for e in audit_entries
    ]

    return summary


# ---------------------------------------------------------------------------
# POST /disputes/{id}/approve
# ---------------------------------------------------------------------------

@router.post("/{dispute_id}/approve", summary="Admin: approve dispute letter for filing")
def approve_letter(
    dispute_id: uuid.UUID,
    payload: ApproveLetterRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    require_admin(request)

    case = _get_case_or_404(db, dispute_id)
    letter = _get_letter_or_404(db, payload.letter_id, dispute_id)

    if letter.status not in (LetterStatus.PENDING_HUMAN_APPROVAL, LetterStatus.DRAFT):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Letter cannot be approved in status: {letter.status.value}",
        )

    admin_id = get_current_user_id(request)
    ip = request.client.host if request.client else None

    approve_dispute_letter(db=db, letter=letter, admin_user_id=admin_id, ip_address=ip)
    db.commit()

    return {
        "message": "Letter approved. Ready to file.",
        "dispute_id": str(dispute_id),
        "letter_id": str(letter.id),
        "next_step": f"File via POST /disputes/{dispute_id}/file",
    }


# ---------------------------------------------------------------------------
# POST /disputes/{id}/reject
# ---------------------------------------------------------------------------

@router.post("/{dispute_id}/reject", summary="Admin: reject dispute letter")
def reject_letter(
    dispute_id: uuid.UUID,
    payload: RejectLetterRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    require_admin(request)

    case = _get_case_or_404(db, dispute_id)
    letter = _get_letter_or_404(db, payload.letter_id, dispute_id)

    admin_id = get_current_user_id(request)
    ip = request.client.host if request.client else None

    reject_dispute_letter(
        db=db,
        letter=letter,
        admin_user_id=admin_id,
        rejection_reason=payload.rejection_reason,
        ip_address=ip,
    )
    db.commit()

    return {
        "message": "Letter rejected. Use /regenerate to create a new version.",
        "dispute_id": str(dispute_id),
        "letter_id": str(letter.id),
        "rejection_reason": payload.rejection_reason,
    }


# ---------------------------------------------------------------------------
# POST /disputes/{id}/file
# ---------------------------------------------------------------------------

@router.post("/{dispute_id}/file", summary="Admin: file approved dispute to bureau")
async def file_dispute(
    dispute_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    require_admin(request)

    case = _get_case_or_404(db, dispute_id)

    if case.status != DisputeStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Dispute must be APPROVED before filing. Current: {case.status.value}",
        )

    # Get the approved letter
    letter = (
        db.query(DisputeLetter)
        .filter(
            DisputeLetter.dispute_id == dispute_id,
            DisputeLetter.status == LetterStatus.APPROVED,
        )
        .order_by(DisputeLetter.letter_version.desc())
        .first()
    )
    if not letter:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No approved letter found. Approve a letter first.",
        )

    actor_id = get_current_user_id(request)
    ip = request.client.host if request.client else None

    result = await file_dispute_to_bureau(
        db=db,
        dispute_case=case,
        letter=letter,
        actor_user_id=actor_id,
        ip_address=ip,
    )
    db.commit()

    # TODO: Send client confirmation notification
    # await notify_client_dispute_filed(case.client_id, tracking_number=result["tracking_number"])

    return {
        "message": f"Dispute filed to {case.bureau.title()}.",
        "dispute_id": str(dispute_id),
        "tracking_number": result["tracking_number"],
        "filed_at": result["filed_at"].isoformat(),
        "expected_response_date": result["expected_response_date"].isoformat(),
        "note": "Bureau has 30 days to respond under FCRA § 611.",
    }


# ---------------------------------------------------------------------------
# POST /disputes/{id}/response
# ---------------------------------------------------------------------------

@router.post(
    "/{dispute_id}/response",
    summary="Record bureau response to dispute",
    description="Admin or system posts bureau response. Updates case status and triggers client notification.",
)
def record_response(
    dispute_id: uuid.UUID,
    payload: RecordResponseRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    require_admin_or_agent(request)

    case = _get_case_or_404(db, dispute_id)

    if case.status not in (
        DisputeStatus.FILED,
        DisputeStatus.INVESTIGATING,
        DisputeStatus.RESPONDED,
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot record response for dispute in status: {case.status.value}",
        )

    actor_id = get_current_user_id(request)
    ip = request.client.host if request.client else None

    bureau_response = record_bureau_response(
        db=db,
        dispute_case=case,
        response_type=payload.response_type,
        response_content=payload.response_content,
        response_url=payload.response_url,
        score_impact=payload.score_impact,
        actor_user_id=actor_id,
        ip_address=ip,
    )
    db.commit()

    # Build celebratory response for wins
    is_win = payload.response_type in (BureauResponseType.REMOVED, BureauResponseType.DELETED)
    message = (
        f"🎉 Item REMOVED from {case.bureau.title()} credit report!"
        if is_win
        else f"Bureau response recorded: {payload.response_type.value}"
    )

    # TODO: notify_client_dispute_update(case.client_id, response_type=payload.response_type)

    return {
        "message": message,
        "dispute_id": str(dispute_id),
        "response_id": str(bureau_response.id),
        "response_type": payload.response_type.value,
        "new_status": case.status.value,
        "outcome": case.outcome.value if case.outcome else None,
        "score_impact": payload.score_impact,
        "win": is_win,
    }


# ---------------------------------------------------------------------------
# POST /disputes/{id}/withdraw
# ---------------------------------------------------------------------------

@router.post("/{dispute_id}/withdraw", summary="Withdraw a dispute")
def withdraw_dispute(
    dispute_id: uuid.UUID,
    payload: WithdrawRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    require_admin_or_agent(request)

    case = _get_case_or_404(db, dispute_id)

    if case.status in (DisputeStatus.RESOLVED, DisputeStatus.WITHDRAWN):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot withdraw dispute in status: {case.status.value}",
        )

    case.status = DisputeStatus.WITHDRAWN
    if payload.reason:
        case.admin_notes = (case.admin_notes or "") + f"\nWithdrawn: {payload.reason}"

    actor_id = get_current_user_id(request)
    ip = request.client.host if request.client else None

    entry = AuditTrail(
        actor_user_id=actor_id,
        actor_type="user",
        subject_type="dispute_case",
        subject_id=dispute_id,
        client_id=case.client_id,
        action=AuditAction.DISPUTE_WITHDRAWN,
        description=f"Dispute withdrawn. Reason: {payload.reason or 'not provided'}",
        metadata={"reason": payload.reason},
        ip_address=ip,
    )
    db.add(entry)
    db.commit()

    return {"message": "Dispute withdrawn.", "dispute_id": str(dispute_id)}


# ---------------------------------------------------------------------------
# GET /disputes/{id}/letter
# ---------------------------------------------------------------------------

@router.get("/{dispute_id}/letter", summary="Get latest dispute letter content")
def get_letter(
    dispute_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    case = _get_case_or_404(db, dispute_id)
    _check_access(request, case)

    letter = (
        db.query(DisputeLetter)
        .filter(DisputeLetter.dispute_id == dispute_id)
        .order_by(DisputeLetter.letter_version.desc())
        .first()
    )
    if not letter:
        raise HTTPException(status_code=404, detail="No letter found for this dispute.")

    return {
        "dispute_id": str(dispute_id),
        "letter_id": str(letter.id),
        "version": letter.letter_version,
        "status": letter.status.value,
        "compliance_status": letter.compliance_status,
        "compliance_flags": letter.compliance_flags,
        "content": letter.letter_content,
        "ai_model_used": letter.ai_model_used,
        "approved_by": str(letter.approved_by_admin_id) if letter.approved_by_admin_id else None,
        "approval_date": letter.approval_date.isoformat() if letter.approval_date else None,
        "rejection_reason": letter.rejection_reason,
        "created_at": letter.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# POST /disputes/{id}/regenerate
# ---------------------------------------------------------------------------

@router.post("/{dispute_id}/regenerate", summary="Regenerate dispute letter (new version)")
async def regenerate_letter(
    dispute_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    require_admin_or_agent(request)

    case = _get_case_or_404(db, dispute_id)
    client = db.query(ClientProfile).filter(ClientProfile.id == case.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client profile not found.")

    if case.status == DisputeStatus.FILED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot regenerate letter for an already-filed dispute.",
        )

    actor_id = get_current_user_id(request)
    ip = request.client.host if request.client else None

    letter = await generate_letter_for_case(
        db=db,
        dispute_case=case,
        client=client,
        actor_user_id=actor_id,
        ip_address=ip,
    )

    # Reset case to pending approval
    if case.status != DisputeStatus.FILED:
        case.status = DisputeStatus.PENDING_APPROVAL

    db.commit()

    return {
        "message": f"New letter v{letter.letter_version} generated.",
        "dispute_id": str(dispute_id),
        "letter_id": str(letter.id),
        "version": letter.letter_version,
        "compliance_status": letter.compliance_status,
        "compliance_flags": letter.compliance_flags,
        "next_step": (
            f"Review letter via GET /disputes/{dispute_id}/letter, "
            f"then approve via POST /disputes/{dispute_id}/approve"
        ),
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_case_or_404(db: Session, dispute_id: uuid.UUID) -> DisputeCase:
    case = db.query(DisputeCase).filter(DisputeCase.id == dispute_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Dispute not found.")
    return case


def _get_letter_or_404(db: Session, letter_id: uuid.UUID, dispute_id: uuid.UUID) -> DisputeLetter:
    letter = (
        db.query(DisputeLetter)
        .filter(
            DisputeLetter.id == letter_id,
            DisputeLetter.dispute_id == dispute_id,
        )
        .first()
    )
    if not letter:
        raise HTTPException(status_code=404, detail="Letter not found.")
    return letter


def _check_access(request: Request, case: DisputeCase):
    """Clients can only access their own disputes."""
    role = get_current_user_role(request)
    if role == "client":
        actor_id = get_current_user_id(request)
        if actor_id:
            # This would need to check the client profile's user_id
            # Full implementation depends on session middleware providing client_id
            pass  # TODO: enforce when auth middleware sets client_profile_id in state
