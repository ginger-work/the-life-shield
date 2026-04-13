"""
Audit Service

FCRA requires a complete, immutable audit trail for all actions on credit data.
This service is called from other services — never called directly from API routes.

Writes are fire-and-forget (sync) to avoid slowing down request processing.
In production, consider moving to async queue (Celery task).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog
from sqlalchemy.orm import Session

from app.models.audit import AuditAction, AuditTrail

log = structlog.get_logger(__name__)


def log_audit(
    db: Session,
    action: AuditAction,
    *,
    actor_user_id: Optional[uuid.UUID] = None,
    actor_agent_id: Optional[uuid.UUID] = None,
    actor_type: str = "system",
    subject_type: Optional[str] = None,
    subject_id: Optional[uuid.UUID] = None,
    client_id: Optional[uuid.UUID] = None,
    description: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,  # mapped to event_data column
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    correlation_id: Optional[str] = None,
    success: bool = True,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> AuditTrail:
    """
    Write an audit log entry.

    This is the single function all other services use to create audit records.
    No PII should be passed in metadata — use IDs and status codes only.

    Args:
        db: SQLAlchemy session
        action: The audit action enum value
        actor_user_id: User who initiated the action
        actor_agent_id: AI agent that performed the action
        actor_type: "user", "agent", "system", "webhook", "cron"
        subject_type: Type of the entity affected ("dispute", "client", etc.)
        subject_id: ID of the entity affected
        client_id: Client whose data was affected (for quick audit queries)
        description: Human-readable description
        metadata: Structured details (no PII)
        ip_address: Request IP address
        user_agent: Request user agent string
        correlation_id: Request correlation ID
        success: Whether the action succeeded
        error_code: Error code if failed
        error_message: Error message if failed (no PII)

    Returns:
        The created AuditTrail record
    """
    entry = AuditTrail(
        actor_user_id=actor_user_id,
        actor_agent_id=actor_agent_id,
        actor_type=actor_type,
        subject_type=subject_type,
        subject_id=subject_id,
        client_id=client_id,
        action=action,
        description=description,
        event_data=metadata or {},  # renamed from metadata to avoid SQLAlchemy conflict
        ip_address=ip_address,
        user_agent=user_agent,
        correlation_id=correlation_id,
        success=success,
        error_code=error_code,
        error_message=error_message,
    )

    try:
        db.add(entry)
        db.flush()  # Get ID without full commit (caller controls commit)
    except Exception as exc:
        log.error(
            "audit_write_failed",
            action=action.value,
            error=str(exc),
        )
        # Audit failures should not block business operations
        # Log to stderr but don't raise

    return entry


def get_client_audit_log(
    db: Session,
    client_id: uuid.UUID,
    limit: int = 100,
    offset: int = 0,
    action_filter: Optional[AuditAction] = None,
) -> list[AuditTrail]:
    """
    Retrieve audit log entries for a specific client.

    Used for compliance reports, admin review, and client transparency.
    """
    query = (
        db.query(AuditTrail)
        .filter(AuditTrail.client_id == client_id)
        .order_by(AuditTrail.created_at.desc())
    )

    if action_filter:
        query = query.filter(AuditTrail.action == action_filter)

    return query.offset(offset).limit(limit).all()


def get_dispute_audit_log(
    db: Session,
    dispute_id: uuid.UUID,
    limit: int = 50,
) -> list[AuditTrail]:
    """Retrieve all audit events for a specific dispute case."""
    return (
        db.query(AuditTrail)
        .filter(
            AuditTrail.subject_type == "dispute",
            AuditTrail.subject_id == dispute_id,
        )
        .order_by(AuditTrail.created_at.asc())
        .limit(limit)
        .all()
    )
