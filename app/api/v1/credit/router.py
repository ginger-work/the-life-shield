"""
Credit Report API Router

Endpoints:
  POST   /api/v1/credit/pull           - Pull credit reports from bureaus
  POST   /api/v1/credit/soft-pull      - Tri-merge soft pull via iSoftPull
  GET    /api/v1/credit/reports        - Get client's latest reports
  GET    /api/v1/credit/reports/{id}   - Get a specific report
  GET    /api/v1/credit/score-history  - Get score trend history
  GET    /api/v1/credit/tradelines     - Get client's tradelines
  GET    /api/v1/credit/tradelines/{id}/mark-disputable  - Flag tradeline for dispute

RBAC:
  - Clients can pull their own reports
  - Admins and staff can pull any client's reports
  - Agent service accounts can pull reports (for analysis)

FCRA Compliance:
  - Every pull is logged in audit_trail
  - Full/hard pulls require explicit consent flag
  - SSN is decrypted only at time of API call, never stored in logs
"""
from __future__ import annotations

import uuid
from typing import List, Optional

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client import ClientProfile, CreditReport, CreditReportSnapshot, Tradeline
from app.schemas.credit import (
    CreditReportResponse,
    LatestReportsResponse,
    CreditScoreSummary,
    PullCreditReportRequest,
    PullCreditReportResponse,
    ScoreHistoryEntry,
    ScoreHistoryResponse,
    SoftPullRequest,
    TradelineResponse,
)
from app.services.credit_report_service import (
    get_latest_reports,
    pull_credit_report,
    pull_soft_pull_tri_merge,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/credit", tags=["Credit Reports"])


def _get_current_user_id(request: Request) -> Optional[uuid.UUID]:
    """Extract current user ID from request state (set by auth middleware)."""
    user_id = getattr(request.state, "user_id", None)
    return uuid.UUID(str(user_id)) if user_id else None


def _get_client_or_404(db: Session, client_id: uuid.UUID) -> ClientProfile:
    client = db.query(ClientProfile).filter(ClientProfile.id == client_id).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "Client not found"},
        )
    return client


def _decrypt_ssn(client: ClientProfile) -> str:
    """
    Decrypt client's SSN for bureau API calls.

    In production: use AWS KMS or application-level AES-256 decryption.
    In sandbox: return a test SSN that drives sandbox scenarios.
    """
    from app.core.config import settings

    if settings.BUREAU_SANDBOX_MODE or settings.is_development:
        # Sandbox SSN — last 4 determines the credit scenario
        # 0000-3333 = excellent, 3334-6666 = fair, 6667-9999 = poor
        ssn_last4 = client.ssn_last_4 or "5000"
        return f"000-00-{ssn_last4}"

    # Production: decrypt the encrypted SSN
    if not client.ssn_encrypted:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "MISSING_SSN",
                "message": "Client SSN not on file. Please complete identity verification.",
            },
        )

    # TODO: Implement AES-256 decryption with AWS KMS
    # encrypted_ssn = client.ssn_encrypted
    # return decrypt_with_kms(encrypted_ssn)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"error": "NOT_IMPLEMENTED", "message": "SSN decryption not configured"},
    )


@router.post(
    "/pull",
    response_model=PullCreditReportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Pull credit reports from bureaus",
    description=(
        "Pull credit reports from one or more bureaus. "
        "Full pulls use client's SSN and may be hard inquiries. "
        "All pulls are logged to the FCRA audit trail. "
        "Requires: disputes:write permission."
    ),
)
def pull_reports(
    client_id: uuid.UUID = Query(..., description="Client ID to pull reports for"),
    payload: PullCreditReportRequest = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """
    Pull credit reports from specified bureaus for a client.

    - **bureaus**: List of bureaus to pull (equifax, experian, transunion)
    - **pull_type**: "full" (hard inquiry), "soft" (no score impact), "monitoring"

    Returns report IDs and success/failure per bureau.
    """
    client = _get_client_or_404(db, client_id)
    decrypted_ssn = _decrypt_ssn(client)
    actor_user_id = _get_current_user_id(request) if request else None
    correlation_id = (
        request.headers.get("X-Correlation-ID") if request else None
    )

    reports = pull_credit_report(
        db=db,
        client=client,
        decrypted_ssn=decrypted_ssn,
        bureaus=payload.bureaus,
        pull_type=payload.pull_type,
        correlation_id=correlation_id,
        actor_user_id=actor_user_id,
    )

    report_ids = {bureau: str(report.id) for bureau, report in reports.items()}
    failed = [b for b in payload.bureaus if b not in reports]

    return PullCreditReportResponse(
        success=len(reports) > 0,
        message=f"Successfully pulled {len(reports)} report(s)",
        reports_pulled=list(reports.keys()),
        reports_failed=failed,
        report_ids=report_ids,
    )


@router.post(
    "/soft-pull",
    response_model=PullCreditReportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Tri-merge soft pull via iSoftPull",
    description=(
        "Pull a tri-merge soft credit report from all three bureaus via iSoftPull. "
        "Does NOT impact consumer's credit score. "
        "Ideal for onboarding and monthly monitoring."
    ),
)
def soft_pull(
    client_id: uuid.UUID = Query(..., description="Client ID"),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """
    Tri-merge soft pull — pulls all 3 bureaus simultaneously, no score impact.
    """
    client = _get_client_or_404(db, client_id)
    decrypted_ssn = _decrypt_ssn(client)
    actor_user_id = _get_current_user_id(request) if request else None
    correlation_id = request.headers.get("X-Correlation-ID") if request else None

    reports = pull_soft_pull_tri_merge(
        db=db,
        client=client,
        decrypted_ssn=decrypted_ssn,
        correlation_id=correlation_id,
        actor_user_id=actor_user_id,
    )

    report_ids = {bureau: str(report.id) for bureau, report in reports.items()}

    return PullCreditReportResponse(
        success=len(reports) > 0,
        message=f"Soft pull complete — {len(reports)} bureau(s)",
        reports_pulled=list(reports.keys()),
        reports_failed=[],
        report_ids=report_ids,
    )


@router.get(
    "/reports",
    response_model=LatestReportsResponse,
    summary="Get client's latest credit reports",
    description="Returns the most recent credit report per bureau for the specified client.",
)
def get_latest(
    client_id: uuid.UUID = Query(..., description="Client ID"),
    db: Session = Depends(get_db),
):
    """Get the most recent credit report for each bureau."""
    client = _get_client_or_404(db, client_id)
    reports = get_latest_reports(db, client_id)

    summaries: dict[str, CreditScoreSummary] = {}
    for rpt in reports:
        summaries[rpt.bureau.value] = CreditScoreSummary(
            bureau=rpt.bureau.value,
            score=rpt.score,
            score_model=rpt.score_model,
            pull_date=rpt.pull_date,
            negative_items_count=rpt.negative_items_count,
            inquiries_count=rpt.inquiries_count,
            tradelines_count=rpt.tradelines_count,
            collections_count=rpt.collections_count,
        )

    return LatestReportsResponse(
        client_id=client_id,
        equifax=summaries.get("equifax"),
        experian=summaries.get("experian"),
        transunion=summaries.get("transunion"),
        scores_updated_at=client.score_updated_at,
        reports=[],  # Full report data excluded from this summary endpoint
    )


@router.get(
    "/reports/{report_id}",
    response_model=CreditReportResponse,
    summary="Get a specific credit report",
    description="Returns full details of a specific credit report including tradelines and inquiries.",
)
def get_report(
    report_id: uuid.UUID = Path(..., description="Credit report ID"),
    db: Session = Depends(get_db),
):
    """Get a specific credit report with full tradeline and inquiry data."""
    report = db.query(CreditReport).filter(CreditReport.id == report_id).first()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "Credit report not found"},
        )

    return CreditReportResponse(
        id=report.id,
        client_id=report.client_id,
        bureau=report.bureau.value,
        pull_date=report.pull_date,
        pull_type=report.pull_type,
        score=report.score,
        score_model=report.score_model,
        report_reference_number=report.report_reference_number,
        negative_items_count=report.negative_items_count,
        inquiries_count=report.inquiries_count,
        tradelines_count=report.tradelines_count,
        collections_count=report.collections_count,
        tradelines=[
            TradelineResponse(
                id=t.id,
                bureau=t.bureau.value,
                creditor_name=t.creditor_name,
                account_type=t.account_type,
                account_number_masked=t.account_number_masked,
                status=t.status.value,
                balance=float(t.balance) if t.balance else None,
                credit_limit=float(t.credit_limit) if t.credit_limit else None,
                original_amount=float(t.original_amount) if t.original_amount else None,
                utilization=t.utilization,
                date_opened=t.date_opened,
                date_reported=t.date_reported,
                is_disputable=t.is_disputable,
                dispute_reason=t.dispute_reason,
                analyst_notes=t.analyst_notes,
            )
            for t in report.tradelines
        ],
        inquiries=[],  # Loaded separately via relationship
    )


@router.get(
    "/score-history",
    response_model=ScoreHistoryResponse,
    summary="Get credit score history",
    description="Returns monthly score snapshots for trend analysis.",
)
def get_score_history(
    client_id: uuid.UUID = Query(..., description="Client ID"),
    months: int = Query(default=12, ge=1, le=36, description="Number of months of history"),
    db: Session = Depends(get_db),
):
    """Get credit score history for trend charts."""
    _get_client_or_404(db, client_id)

    snapshots = (
        db.query(CreditReportSnapshot)
        .filter(CreditReportSnapshot.client_id == client_id)
        .order_by(CreditReportSnapshot.snapshot_date.desc())
        .limit(months)
        .all()
    )

    history = [
        ScoreHistoryEntry(
            snapshot_date=s.snapshot_date,
            score_equifax=s.score_equifax,
            score_experian=s.score_experian,
            score_transunion=s.score_transunion,
            negative_items_count=s.negative_items_count,
            inquiries_count=s.inquiries_count,
        )
        for s in reversed(snapshots)  # Oldest first for chart rendering
    ]

    return ScoreHistoryResponse(client_id=client_id, history=history)


@router.get(
    "/tradelines",
    response_model=List[TradelineResponse],
    summary="Get client tradelines",
    description="Returns all tradelines for a client, optionally filtered by bureau or disputable status.",
)
def get_tradelines(
    client_id: uuid.UUID = Query(..., description="Client ID"),
    bureau: Optional[str] = Query(default=None, description="Filter by bureau"),
    disputable_only: bool = Query(default=False, description="Only return disputable items"),
    db: Session = Depends(get_db),
):
    """Get tradelines for a client with optional filtering."""
    _get_client_or_404(db, client_id)

    query = db.query(Tradeline).filter(Tradeline.client_id == client_id)

    if bureau:
        query = query.filter(Tradeline.bureau == bureau.lower())
    if disputable_only:
        query = query.filter(Tradeline.is_disputable == True)

    tradelines = query.order_by(Tradeline.date_reported.desc()).all()

    return [
        TradelineResponse(
            id=t.id,
            bureau=t.bureau.value,
            creditor_name=t.creditor_name,
            account_type=t.account_type,
            account_number_masked=t.account_number_masked,
            status=t.status.value,
            balance=float(t.balance) if t.balance else None,
            credit_limit=float(t.credit_limit) if t.credit_limit else None,
            original_amount=float(t.original_amount) if t.original_amount else None,
            utilization=t.utilization,
            date_opened=t.date_opened,
            date_reported=t.date_reported,
            is_disputable=t.is_disputable,
            dispute_reason=t.dispute_reason,
            analyst_notes=t.analyst_notes,
        )
        for t in tradelines
    ]


@router.patch(
    "/tradelines/{tradeline_id}/mark-disputable",
    response_model=TradelineResponse,
    summary="Mark a tradeline as disputable",
    description="Analyst marks a tradeline as disputable with a reason. Required before creating a dispute case.",
)
def mark_tradeline_disputable(
    tradeline_id: uuid.UUID = Path(..., description="Tradeline ID"),
    dispute_reason: str = Query(..., description="Reason the item is disputable"),
    analyst_notes: Optional[str] = Query(default=None, description="Analyst notes"),
    db: Session = Depends(get_db),
):
    """Mark a tradeline as disputable."""
    tradeline = db.query(Tradeline).filter(Tradeline.id == tradeline_id).first()
    if not tradeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "Tradeline not found"},
        )

    tradeline.is_disputable = True
    tradeline.dispute_reason = dispute_reason
    if analyst_notes:
        tradeline.analyst_notes = analyst_notes

    return TradelineResponse(
        id=tradeline.id,
        bureau=tradeline.bureau.value,
        creditor_name=tradeline.creditor_name,
        account_type=tradeline.account_type,
        account_number_masked=tradeline.account_number_masked,
        status=tradeline.status.value,
        balance=float(tradeline.balance) if tradeline.balance else None,
        credit_limit=float(tradeline.credit_limit) if tradeline.credit_limit else None,
        original_amount=float(tradeline.original_amount) if tradeline.original_amount else None,
        utilization=tradeline.utilization,
        date_opened=tradeline.date_opened,
        date_reported=tradeline.date_reported,
        is_disputable=tradeline.is_disputable,
        dispute_reason=tradeline.dispute_reason,
        analyst_notes=tradeline.analyst_notes,
    )
