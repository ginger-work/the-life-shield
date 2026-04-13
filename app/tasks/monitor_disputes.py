"""
Dispute Status Monitor — Background Task

Runs periodically (every 7 days) to:
1. Check status of all open disputes
2. Flag overdue investigations (30-day FCRA window exceeded)
3. Send client notifications about status changes
4. Generate status reports

Can be triggered:
- Via Celery beat schedule (production)
- Via management command / cron job
- Via test utilities

FCRA: Bureaus have 30 days to investigate (§ 611). System must track this.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Main monitoring task
# ---------------------------------------------------------------------------

async def monitor_all_disputes(db_session=None) -> dict:
    """
    Main monitoring loop. Checks all open disputes and takes action.

    Returns a summary dict with counts of actions taken.
    """
    from app.core.database import get_db_context
    from app.models.dispute import DisputeCase, DisputeStatus
    from app.api.disputes.service import get_overdue_disputes, get_disputes_needing_check

    summary = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overdue_flagged": 0,
        "status_checks_triggered": 0,
        "notifications_sent": 0,
        "errors": [],
    }

    context = db_session or get_db_context()

    try:
        with context as db:
            # 1. Flag overdue disputes
            overdue = get_overdue_disputes(db)
            for case in overdue:
                try:
                    await _handle_overdue_dispute(db, case)
                    summary["overdue_flagged"] += 1
                except Exception as exc:
                    err = f"Overdue handling failed for {case.id}: {exc}"
                    logger.error(err, exc_info=exc)
                    summary["errors"].append(err)

            # 2. Trigger 7-day status checks for active disputes
            active = get_disputes_needing_check(db, days=7)
            for case in active:
                try:
                    await _check_dispute_status(db, case)
                    summary["status_checks_triggered"] += 1
                except Exception as exc:
                    err = f"Status check failed for {case.id}: {exc}"
                    logger.error(err, exc_info=exc)
                    summary["errors"].append(err)

            db.commit()

    except Exception as exc:
        logger.error("Dispute monitor task failed", exc_info=exc)
        summary["errors"].append(str(exc))

    logger.info(
        "Dispute monitoring complete",
        overdue=summary["overdue_flagged"],
        checked=summary["status_checks_triggered"],
        errors=len(summary["errors"]),
    )
    return summary


# ---------------------------------------------------------------------------
# Handle overdue dispute
# ---------------------------------------------------------------------------

async def _handle_overdue_dispute(db, case) -> None:
    """
    Dispute has exceeded the 30-day FCRA investigation window.
    Under FCRA § 611(a)(3), if the bureau fails to complete investigation
    in 30 days, they must delete the item.

    Action:
    - Update status to INVESTIGATING (mark as overdue)
    - Log audit entry
    - Queue notification to client and admin
    """
    from app.models.audit import AuditAction, AuditTrail
    from app.models.dispute import DisputeStatus

    logger.warning(
        "Dispute overdue — bureau exceeded 30-day window",
        case_id=str(case.id),
        bureau=case.bureau,
        filed_date=case.filed_date.isoformat() if case.filed_date else None,
    )

    # Move to INVESTIGATING to flag for human review
    if case.status == DisputeStatus.FILED:
        case.status = DisputeStatus.INVESTIGATING

    days_overdue = 0
    if case.expected_response_date:
        days_overdue = (datetime.now(timezone.utc) - case.expected_response_date).days

    entry = AuditTrail(
        actor_type="cron",
        subject_type="dispute_case",
        subject_id=case.id,
        client_id=case.client_id,
        action=AuditAction.DISPUTE_STATUS_UPDATED,
        description=(
            f"OVERDUE: Bureau {case.bureau} has not responded in 30 days "
            f"({days_overdue} days overdue). FCRA § 611 violation possible."
        ),
        metadata={
            "days_overdue": days_overdue,
            "expected_response_date": (
                case.expected_response_date.isoformat()
                if case.expected_response_date
                else None
            ),
            "action": "flagged_overdue",
        },
    )
    db.add(entry)

    # TODO: notify_admin_overdue_dispute(case)
    # TODO: notify_client_overdue_update(case)


# ---------------------------------------------------------------------------
# Check dispute status (periodic 7-day check)
# ---------------------------------------------------------------------------

async def _check_dispute_status(db, case) -> None:
    """
    Periodic check for a single dispute.
    In a real integration, this would call the bureau's status API.
    Currently: logs the check to audit trail.
    """
    from app.models.audit import AuditAction, AuditTrail

    days_since_filing = 0
    if case.filed_date:
        days_since_filing = (datetime.now(timezone.utc) - case.filed_date).days

    entry = AuditTrail(
        actor_type="cron",
        subject_type="dispute_case",
        subject_id=case.id,
        client_id=case.client_id,
        action=AuditAction.DISPUTE_STATUS_UPDATED,
        description=f"7-day status check: Day {days_since_filing} of investigation",
        metadata={
            "days_since_filing": days_since_filing,
            "check_type": "7_day_periodic",
            "current_status": case.status.value,
        },
    )
    db.add(entry)

    logger.info(
        "Dispute status check",
        case_id=str(case.id),
        bureau=case.bureau,
        days_since_filing=days_since_filing,
        status=case.status.value,
    )


# ---------------------------------------------------------------------------
# Generate client report for resolved cases
# ---------------------------------------------------------------------------

def generate_resolution_report(case, bureau_response=None) -> dict:
    """
    Generate a resolution report for a resolved dispute.
    Used for client notifications and admin dashboard.
    """
    from app.models.dispute import BureauResponseType

    is_win = case.outcome in (BureauResponseType.REMOVED, BureauResponseType.DELETED)

    days_to_resolve = None
    if case.filed_date and case.outcome_date:
        days_to_resolve = (case.outcome_date - case.filed_date).days

    return {
        "dispute_id": str(case.id),
        "client_id": str(case.client_id),
        "bureau": case.bureau.title(),
        "creditor": case.creditor_name,
        "outcome": case.outcome.value if case.outcome else None,
        "is_win": is_win,
        "score_impact": case.score_impact_points,
        "days_to_resolve": days_to_resolve,
        "filed_date": case.filed_date.isoformat() if case.filed_date else None,
        "resolved_date": case.outcome_date.isoformat() if case.outcome_date else None,
        "win_message": (
            f"🎉 Great news! The {case.bureau.title()} has REMOVED the "
            f"{case.creditor_name or 'disputed item'} from your credit report!"
            + (f" Your score may improve by approximately {case.score_impact_points} points."
               if case.score_impact_points else "")
        ) if is_win else None,
        "verified_message": (
            f"The {case.bureau.title()} verified the {case.creditor_name or 'item'} "
            f"as accurate after investigation. We can explore other dispute strategies "
            f"if you believe this is still inaccurate."
        ) if not is_win and case.outcome else None,
    }


# ---------------------------------------------------------------------------
# Celery task definition (optional — used if Celery is configured)
# ---------------------------------------------------------------------------

def register_celery_tasks(celery_app):
    """
    Register dispute monitoring tasks with Celery.
    Call this during app startup if using Celery.

    Usage:
        from app.tasks.monitor_disputes import register_celery_tasks
        register_celery_tasks(celery_app)
    """
    import asyncio

    @celery_app.task(name="disputes.monitor_all", bind=True, max_retries=3)
    def monitor_disputes_task(self):
        """Celery task: monitor all active disputes."""
        try:
            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(monitor_all_disputes())
            logger.info("Celery dispute monitor complete", result=result)
            return result
        except Exception as exc:
            logger.error("Celery dispute monitor failed", exc_info=exc)
            raise self.retry(exc=exc, countdown=60 * 15)  # Retry in 15 minutes

    @celery_app.task(name="disputes.check_single", bind=True, max_retries=2)
    def check_single_dispute_task(self, dispute_id: str):
        """Celery task: check a single dispute by ID."""
        from app.core.database import get_db_context
        from app.models.dispute import DisputeCase

        try:
            with get_db_context() as db:
                case = db.query(DisputeCase).filter(
                    DisputeCase.id == uuid.UUID(dispute_id)
                ).first()
                if case:
                    loop = asyncio.get_event_loop()
                    loop.run_until_complete(_check_dispute_status(db, case))
                    db.commit()
        except Exception as exc:
            raise self.retry(exc=exc, countdown=60 * 5)

    return monitor_disputes_task, check_single_dispute_task
