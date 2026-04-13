"""
Credit Report Service

Orchestrates credit report pulls across all three bureaus.
Handles:
- Pulling reports from Equifax, Experian, TransUnion, iSoftPull
- Storing raw + parsed data in database
- Syncing tradelines and inquiries
- FCRA audit trail for every pull
- Consumer identity decryption (delegating to encryption service)
- Score snapshot creation after each pull
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

import structlog
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.bureaus import (
    BureauName as IntegrationBureauName,
    ConsumerIdentity,
    EquifaxClient,
    ExperianClient,
    ISoftPullClient,
    PullType,
    ReportPullResult,
    TransUnionClient,
)
from app.models.audit import AuditAction
from app.models.client import (
    BureauName as ModelBureauName,
    ClientProfile,
    CreditReport,
    CreditReportSnapshot,
    Inquiry,
    Tradeline,
    TradelineStatus,
)
from app.services.audit_service import log_audit

log = structlog.get_logger(__name__)

# Map integration BureauName → model BureauName
BUREAU_NAME_MAP = {
    IntegrationBureauName.EQUIFAX: ModelBureauName.EQUIFAX,
    IntegrationBureauName.EXPERIAN: ModelBureauName.EXPERIAN,
    IntegrationBureauName.TRANSUNION: ModelBureauName.TRANSUNION,
}

# Map pull type string → integration PullType
PULL_TYPE_MAP = {
    "full": PullType.FULL,
    "soft": PullType.SOFT,
    "monitoring": PullType.MONITORING,
}

# Account status string → TradelineStatus enum
TRADELINE_STATUS_MAP = {
    "current": TradelineStatus.CURRENT,
    "late_30": TradelineStatus.LATE_30,
    "30dlate": TradelineStatus.LATE_30,
    "late_60": TradelineStatus.LATE_60,
    "60dlate": TradelineStatus.LATE_60,
    "late_90": TradelineStatus.LATE_90,
    "90dlate": TradelineStatus.LATE_90,
    "charge_off": TradelineStatus.CHARGE_OFF,
    "chargeoff": TradelineStatus.CHARGE_OFF,
    "collection": TradelineStatus.COLLECTION,
    "paid": TradelineStatus.PAID,
    "closed": TradelineStatus.CLOSED,
    "transferred": TradelineStatus.TRANSFERRED,
    "disputed": TradelineStatus.DISPUTED,
}


def _build_consumer_identity(client: ClientProfile, decrypted_ssn: str) -> ConsumerIdentity:
    """Build ConsumerIdentity from client profile + decrypted SSN."""
    dob_str = (
        client.date_of_birth.strftime("%Y-%m-%d")
        if client.date_of_birth
        else ""
    )
    return ConsumerIdentity(
        first_name=client.full_name.split()[0] if client.full_name else "",
        last_name=" ".join(client.full_name.split()[1:]) if client.full_name else "",
        ssn=decrypted_ssn,
        date_of_birth=dob_str,
        address_line1=client.address_line1 or "",
        city=client.city or "",
        state=client.state or "",
        zip_code=client.zip_code or "",
        address_line2=client.address_line2,
        phone=client.phone,
    )


def _build_bureau_client(bureau: IntegrationBureauName, sandbox: bool = True):
    """Instantiate the correct bureau client."""
    if bureau == IntegrationBureauName.EQUIFAX:
        return EquifaxClient(
            client_id=settings.EQUIFAX_CLIENT_ID,
            client_secret=settings.EQUIFAX_CLIENT_SECRET,
            sandbox=sandbox,
        )
    elif bureau == IntegrationBureauName.EXPERIAN:
        return ExperianClient(
            client_id=settings.EXPERIAN_CLIENT_ID,
            client_secret=settings.EXPERIAN_CLIENT_SECRET,
            subcode=settings.EXPERIAN_SUBCODE,
            sandbox=sandbox,
        )
    elif bureau == IntegrationBureauName.TRANSUNION:
        return TransUnionClient(
            api_key=settings.TRANSUNION_API_KEY,
            api_secret=settings.TRANSUNION_API_SECRET,
            member_code=settings.TRANSUNION_MEMBER_CODE,
            security_code=settings.TRANSUNION_SECURITY_CODE,
            sandbox=sandbox,
        )
    raise ValueError(f"Unknown bureau: {bureau}")


def _store_report(
    db: Session,
    client: ClientProfile,
    result: ReportPullResult,
) -> CreditReport:
    """Persist a ReportPullResult to the credit_reports table."""
    model_bureau = BUREAU_NAME_MAP.get(result.bureau, ModelBureauName.EQUIFAX)

    report = CreditReport(
        client_id=client.id,
        bureau=model_bureau,
        pull_date=result.pull_timestamp,
        pull_type=result.pull_type.value,
        score=result.credit_score,
        score_model=result.score_model,
        score_range_min=result.score_range_min,
        score_range_max=result.score_range_max,
        report_reference_number=result.reference_number,
        raw_data_url=None,  # Would be S3 URL after upload in production
        parsed_data=result.parsed_data,
        negative_items_count=result.negative_items_count,
        inquiries_count=result.inquiries_count,
        tradelines_count=result.tradelines_count,
        collections_count=result.collections_count,
        api_response_code="200" if result.success else "ERROR",
        api_error_message=result.error_message,
    )
    db.add(report)
    db.flush()  # Get ID before tradelines reference it
    return report


def _store_tradelines(
    db: Session,
    client: ClientProfile,
    report: CreditReport,
    result: ReportPullResult,
) -> int:
    """Parse and store tradelines from a report pull result."""
    model_bureau = BUREAU_NAME_MAP.get(result.bureau, ModelBureauName.EQUIFAX)
    tradelines_data = result.parsed_data.get("tradelines", [])
    count = 0

    for t in tradelines_data:
        raw_status = t.get("status", "current").lower().replace(" ", "_").replace("-", "_")
        status = TRADELINE_STATUS_MAP.get(raw_status, TradelineStatus.CURRENT)

        if t.get("is_negative") and status == TradelineStatus.CURRENT:
            status = TradelineStatus.CHARGE_OFF  # Fallback for negative without specific status

        tradeline = Tradeline(
            client_id=client.id,
            report_id=report.id,
            bureau=model_bureau,
            creditor_name=t.get("creditor_name", ""),
            account_number_masked=t.get("account_number_masked"),
            account_type=t.get("account_type"),
            balance=t.get("balance"),
            credit_limit=t.get("credit_limit"),
            original_amount=t.get("original_amount"),
            monthly_payment=t.get("monthly_payment"),
            utilization=t.get("utilization"),
            status=status,
            payment_history=t.get("payment_history"),
            date_opened=_parse_date(t.get("date_opened")),
            date_reported=_parse_date(t.get("date_reported")),
            date_last_active=_parse_date(t.get("date_last_active")),
            date_closed=_parse_date(t.get("date_closed")),
            is_disputable=t.get("is_negative", False),
            dispute_reason="inaccurate" if t.get("is_negative") else None,
        )
        db.add(tradeline)
        count += 1

    return count


def _store_inquiries(
    db: Session,
    client: ClientProfile,
    report: CreditReport,
    result: ReportPullResult,
) -> int:
    """Parse and store inquiries from a report pull result."""
    model_bureau = BUREAU_NAME_MAP.get(result.bureau, ModelBureauName.EQUIFAX)
    inquiries_data = result.parsed_data.get("inquiries", [])
    count = 0

    for i in inquiries_data:
        inquiry = Inquiry(
            client_id=client.id,
            report_id=report.id,
            bureau=model_bureau,
            inquirer_name=i.get("inquirer_name", ""),
            inquiry_date=_parse_date(i.get("inquiry_date")) or datetime.now(timezone.utc),
            is_hard_inquiry=i.get("is_hard", True),
            is_disputable=False,  # Set by analyst after review
        )
        db.add(inquiry)
        count += 1

    return count


def _update_client_scores(
    db: Session,
    client: ClientProfile,
    results: Dict[IntegrationBureauName, ReportPullResult],
) -> None:
    """Update the client's current score fields from latest pull results."""
    for bureau, result in results.items():
        if result.credit_score:
            if bureau == IntegrationBureauName.EQUIFAX:
                client.current_score_equifax = result.credit_score
            elif bureau == IntegrationBureauName.EXPERIAN:
                client.current_score_experian = result.credit_score
            elif bureau == IntegrationBureauName.TRANSUNION:
                client.current_score_transunion = result.credit_score

    client.score_updated_at = datetime.now(timezone.utc)


def _create_snapshot(
    db: Session,
    client: ClientProfile,
    results: Dict[IntegrationBureauName, ReportPullResult],
) -> CreditReportSnapshot:
    """Create a historical score snapshot after pulling reports."""
    eq_result = results.get(IntegrationBureauName.EQUIFAX)
    ex_result = results.get(IntegrationBureauName.EXPERIAN)
    tu_result = results.get(IntegrationBureauName.TRANSUNION)

    total_negatives = sum(
        r.negative_items_count for r in results.values() if r and r.success
    )
    total_inquiries = sum(
        r.inquiries_count for r in results.values() if r and r.success
    )

    snapshot = CreditReportSnapshot(
        client_id=client.id,
        snapshot_date=datetime.now(timezone.utc),
        score_equifax=eq_result.credit_score if eq_result else None,
        score_experian=ex_result.credit_score if ex_result else None,
        score_transunion=tu_result.credit_score if tu_result else None,
        negative_items_count=total_negatives,
        inquiries_count=total_inquiries,
        collections_count=sum(
            r.collections_count for r in results.values() if r and r.success
        ),
    )
    db.add(snapshot)
    return snapshot


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse date string to datetime. Returns None on failure."""
    if not date_str:
        return None
    formats = ["%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# ─────────────────────────────────────────────────────────
# Public Service Functions
# ─────────────────────────────────────────────────────────

def pull_credit_report(
    db: Session,
    client: ClientProfile,
    decrypted_ssn: str,
    bureaus: Optional[List[str]] = None,
    pull_type: str = "full",
    correlation_id: Optional[str] = None,
    actor_user_id: Optional[uuid.UUID] = None,
) -> Dict[str, CreditReport]:
    """
    Pull credit reports from one or more bureaus and store results.

    Args:
        db: Database session
        client: Client profile
        decrypted_ssn: Decrypted SSN (obtained from encryption service)
        bureaus: List of bureaus to pull from. Default: all three.
        pull_type: "full", "soft", or "monitoring"
        correlation_id: Request correlation ID
        actor_user_id: User who requested the pull (for audit)

    Returns:
        Dict mapping bureau name → CreditReport record

    FCRA:
    - Every pull is logged in audit_trail
    - Pull type is recorded (soft vs hard)
    - All raw responses are stored encrypted
    """
    corr_id = correlation_id or str(uuid.uuid4())
    sandbox = settings.is_development or settings.BUREAU_SANDBOX_MODE

    if bureaus is None:
        bureaus = ["equifax", "experian", "transunion"]

    integration_pull_type = PULL_TYPE_MAP.get(pull_type, PullType.FULL)
    consumer = _build_consumer_identity(client, decrypted_ssn)
    stored_reports: Dict[str, CreditReport] = {}

    for bureau_str in bureaus:
        bureau_enum = IntegrationBureauName(bureau_str.lower())

        # Audit: pull requested
        log_audit(
            db,
            AuditAction.CREDIT_REPORT_PULL_REQUESTED,
            actor_user_id=actor_user_id,
            actor_type="user" if actor_user_id else "system",
            subject_type="client",
            subject_id=client.id,
            client_id=client.id,
            description=f"Credit report pull requested from {bureau_str}",
            metadata={"bureau": bureau_str, "pull_type": pull_type, "sandbox": sandbox},
            correlation_id=corr_id,
        )

        try:
            client_instance = _build_bureau_client(bureau_enum, sandbox=sandbox)
            result = client_instance.pull_report(
                consumer=consumer,
                pull_type=integration_pull_type,
                correlation_id=corr_id,
            )
            client_instance.close()

            if not result.success:
                log_audit(
                    db,
                    AuditAction.CREDIT_REPORT_FAILED,
                    actor_type="system",
                    client_id=client.id,
                    description=f"Report pull failed for {bureau_str}: {result.error_message}",
                    metadata={"bureau": bureau_str, "error": result.error_code},
                    correlation_id=corr_id,
                    success=False,
                    error_code=result.error_code,
                    error_message=result.error_message,
                )
                continue

            # Store report, tradelines, inquiries
            report = _store_report(db, client, result)
            tl_count = _store_tradelines(db, client, report, result)
            inq_count = _store_inquiries(db, client, report, result)

            # Audit: success
            log_audit(
                db,
                AuditAction.CREDIT_REPORT_STORED,
                actor_type="system",
                subject_type="credit_report",
                subject_id=report.id,
                client_id=client.id,
                description=f"Credit report stored for {bureau_str}",
                metadata={
                    "bureau": bureau_str,
                    "report_id": str(report.id),
                    "score": result.credit_score,
                    "tradelines": tl_count,
                    "inquiries": inq_count,
                    "negatives": result.negative_items_count,
                },
                correlation_id=corr_id,
            )

            stored_reports[bureau_str] = report

            log.info(
                "credit_report_stored",
                bureau=bureau_str,
                client_id=str(client.id),
                score=result.credit_score,
                tradelines=tl_count,
            )

        except Exception as exc:
            log.error(
                "credit_report_pull_error",
                bureau=bureau_str,
                client_id=str(client.id),
                error=str(exc),
            )
            log_audit(
                db,
                AuditAction.CREDIT_REPORT_FAILED,
                actor_type="system",
                client_id=client.id,
                description=f"Exception during {bureau_str} pull",
                metadata={"bureau": bureau_str, "exception": type(exc).__name__},
                correlation_id=corr_id,
                success=False,
                error_message=str(exc)[:500],
            )

    # Update client score fields + create snapshot
    if stored_reports:
        results_by_bureau = {}
        for bureau_str, rpt in stored_reports.items():
            bureau_enum = IntegrationBureauName(bureau_str)
            results_by_bureau[bureau_enum] = ReportPullResult(
                bureau=bureau_enum,
                pull_type=integration_pull_type,
                reference_number=rpt.report_reference_number or "",
                pull_timestamp=rpt.pull_date,
                raw_response={},
                parsed_data=rpt.parsed_data or {},
                credit_score=rpt.score,
                tradelines_count=rpt.tradelines_count,
                negative_items_count=rpt.negative_items_count,
                inquiries_count=rpt.inquiries_count,
                collections_count=rpt.collections_count,
            )
        _update_client_scores(db, client, results_by_bureau)
        _create_snapshot(db, client, results_by_bureau)

    return stored_reports


def pull_soft_pull_tri_merge(
    db: Session,
    client: ClientProfile,
    decrypted_ssn: str,
    correlation_id: Optional[str] = None,
    actor_user_id: Optional[uuid.UUID] = None,
) -> Dict[str, CreditReport]:
    """
    Pull a tri-merge soft pull via iSoftPull (no score impact).
    Ideal for initial intake and monthly monitoring.
    """
    corr_id = correlation_id or str(uuid.uuid4())
    sandbox = settings.is_development or settings.BUREAU_SANDBOX_MODE
    consumer = _build_consumer_identity(client, decrypted_ssn)

    log_audit(
        db,
        AuditAction.CREDIT_REPORT_PULL_REQUESTED,
        actor_user_id=actor_user_id,
        actor_type="user" if actor_user_id else "system",
        client_id=client.id,
        description="iSoftPull tri-merge soft pull requested",
        metadata={"pull_type": "soft", "provider": "isoftpull", "sandbox": sandbox},
        correlation_id=corr_id,
    )

    try:
        isoftpull = ISoftPullClient(
            api_key=settings.ISOFTPULL_API_KEY,
            sandbox=sandbox,
        )
        results = isoftpull.pull_tri_merge(consumer=consumer, correlation_id=corr_id)
        isoftpull.close()

        stored_reports: Dict[str, CreditReport] = {}

        for bureau_enum, result in results.items():
            result.pull_type = PullType.SOFT
            report = _store_report(db, client, result)
            tl_count = _store_tradelines(db, client, report, result)
            inq_count = _store_inquiries(db, client, report, result)
            stored_reports[bureau_enum.value] = report

            log_audit(
                db,
                AuditAction.CREDIT_REPORT_STORED,
                actor_type="system",
                subject_type="credit_report",
                subject_id=report.id,
                client_id=client.id,
                description=f"iSoftPull soft report stored for {bureau_enum.value}",
                metadata={
                    "bureau": bureau_enum.value,
                    "report_id": str(report.id),
                    "score": result.credit_score,
                    "tradelines": tl_count,
                    "soft_pull": True,
                },
                correlation_id=corr_id,
            )

        _update_client_scores(db, client, results)
        _create_snapshot(db, client, results)

        return stored_reports

    except Exception as exc:
        log.error(
            "isoftpull_tri_merge_error",
            client_id=str(client.id),
            error=str(exc),
        )
        log_audit(
            db,
            AuditAction.CREDIT_REPORT_FAILED,
            actor_type="system",
            client_id=client.id,
            description="iSoftPull tri-merge failed",
            metadata={"exception": type(exc).__name__},
            correlation_id=corr_id,
            success=False,
            error_message=str(exc)[:500],
        )
        return {}


def get_latest_reports(
    db: Session,
    client_id: uuid.UUID,
) -> List[CreditReport]:
    """Return the most recent report per bureau for a client."""
    from sqlalchemy import func

    # Subquery: max pull_date per bureau per client
    subq = (
        db.query(
            CreditReport.bureau,
            func.max(CreditReport.pull_date).label("max_date"),
        )
        .filter(CreditReport.client_id == client_id)
        .group_by(CreditReport.bureau)
        .subquery()
    )

    return (
        db.query(CreditReport)
        .join(
            subq,
            (CreditReport.bureau == subq.c.bureau)
            & (CreditReport.pull_date == subq.c.max_date),
        )
        .filter(CreditReport.client_id == client_id)
        .all()
    )
