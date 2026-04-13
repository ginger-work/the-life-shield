"""
Audit Trail Model

FCRA mandates a complete audit trail for all actions taken on credit data.
Every read, write, file, and decision must be logged immutably.

Tables:
- audit_trail    (immutable log of all system actions)
"""
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditAction(str, PyEnum):
    # Auth actions
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_FAILED = "auth.failed"
    AUTH_TOKEN_REFRESH = "auth.token_refresh"

    # Client actions
    CLIENT_CREATED = "client.created"
    CLIENT_UPDATED = "client.updated"
    CLIENT_DELETED = "client.deleted"
    CLIENT_VIEWED = "client.viewed"

    # Credit report actions
    CREDIT_REPORT_PULL_REQUESTED = "credit.report.pull_requested"
    CREDIT_REPORT_PULLED = "credit.report.pulled"
    CREDIT_REPORT_STORED = "credit.report.stored"
    CREDIT_REPORT_VIEWED = "credit.report.viewed"
    CREDIT_REPORT_FAILED = "credit.report.failed"

    # Dispute actions
    DISPUTE_CREATED = "dispute.created"
    DISPUTE_LETTER_GENERATED = "dispute.letter.generated"
    DISPUTE_LETTER_COMPLIANCE_CHECKED = "dispute.letter.compliance_checked"
    DISPUTE_LETTER_APPROVED = "dispute.letter.approved"
    DISPUTE_LETTER_REJECTED = "dispute.letter.rejected"
    DISPUTE_FILED = "dispute.filed"
    DISPUTE_STATUS_UPDATED = "dispute.status_updated"
    DISPUTE_RESPONSE_RECEIVED = "dispute.response_received"
    DISPUTE_RESOLVED = "dispute.resolved"
    DISPUTE_WITHDRAWN = "dispute.withdrawn"

    # Bureau webhook
    WEBHOOK_RECEIVED = "webhook.received"
    WEBHOOK_PROCESSED = "webhook.processed"
    WEBHOOK_FAILED = "webhook.failed"

    # Admin actions
    ADMIN_VIEWED_CLIENT = "admin.viewed_client"
    ADMIN_OVERRIDE = "admin.override"

    # Compliance
    COMPLIANCE_FLAG_RAISED = "compliance.flag_raised"
    COMPLIANCE_CLEARED = "compliance.cleared"


class AuditTrail(Base):
    """
    Immutable audit log — no updates, no deletes.

    FCRA Compliance:
    - Every credit bureau call must be logged (§ 609 / § 611)
    - Every dispute action must be logged with timestamps
    - Logs retained per data retention policy (minimum 7 years for credit data)
    - No PII in the log — reference by IDs only
    """
    __tablename__ = "audit_trail"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    # Actor — who performed the action
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        doc="User who initiated the action (null for system/automated actions)",
    )
    actor_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        doc="AI agent that performed the action",
    )
    actor_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="system",
        doc="user, agent, system, webhook, cron",
    )

    # Subject — what the action was performed on
    subject_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="client, dispute, letter, report, user, etc.",
    )
    subject_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    # Client context
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        doc="Client whose data was affected (for quick client audit queries)",
    )

    # Action
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, name="audit_action_enum"),
        nullable=False,
        index=True,
    )

    # Details
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Human-readable description of what happened",
    )
    metadata: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Structured details (no PII — IDs, statuses, codes only)",
    )

    # Request context
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)  # IPv6 max 45 chars
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        doc="Request correlation ID for tracing across services",
    )

    # Result
    success: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
    )
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_audit_trail_client_action", "client_id", "action"),
        Index("ix_audit_trail_subject", "subject_type", "subject_id"),
        Index("ix_audit_trail_actor_user", "actor_user_id", "created_at"),
        Index("ix_audit_trail_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<AuditTrail id={self.id} action={self.action} at={self.created_at}>"
