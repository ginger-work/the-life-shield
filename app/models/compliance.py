"""
Compliance & Escalation Models

Tracks FCRA/CROA compliance events, human takeovers, and escalations.

Tables:
- escalation_events   (when system escalates to human review)
- human_takeovers     (when a human agent takes over from AI)
"""
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.client import ClientProfile


class EscalationReason(str, PyEnum):
    COMPLIANCE_FLAG = "compliance_flag"           # AI flagged potential FCRA/CROA violation
    HUMAN_REQUESTED = "human_requested"           # Client requested human
    SENSITIVE_TOPIC = "sensitive_topic"           # Topic requires human judgment
    DISPUTE_REVIEW = "dispute_review"             # Dispute needs human approval
    FRAUD_SUSPECTED = "fraud_suspected"           # Potential fraud detected
    SYSTEM_ERROR = "system_error"                 # AI encountered an error
    HIGH_VALUE_DECISION = "high_value_decision"   # Decision above AI authority threshold
    COMPLAINT_RECEIVED = "complaint_received"     # Client filed complaint


class EscalationStatus(str, PyEnum):
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class EscalationEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Records when the system escalates a situation to human review.
    Required for FCRA/CROA compliance when AI cannot proceed without human judgment.
    """
    __tablename__ = "escalation_events"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    triggered_by_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        doc="AI agent that triggered this escalation",
    )
    assigned_to_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        doc="Human staff member assigned to resolve",
    )

    reason: Mapped[EscalationReason] = mapped_column(
        Enum(EscalationReason, name="escalation_reason_enum"),
        nullable=False,
        index=True,
    )
    status: Mapped[EscalationStatus] = mapped_column(
        Enum(EscalationStatus, name="escalation_status_enum"),
        nullable=False,
        default=EscalationStatus.OPEN,
        index=True,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="What triggered the escalation and why",
    )
    context_data: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Relevant context (dispute ID, compliance flags, etc.)",
    )

    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Relationships ---
    client: Mapped["ClientProfile"] = relationship(
        "ClientProfile",
        back_populates="escalation_events",
    )

    __table_args__ = (
        Index("ix_escalation_events_status", "status"),
        Index("ix_escalation_events_client_status", "client_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<EscalationEvent id={self.id} reason={self.reason} status={self.status}>"


class HumanTakeover(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Records when a human staff member takes over an AI conversation/workflow.
    The AI pauses its actions during a takeover.
    """
    __tablename__ = "human_takeovers"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    human_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        doc="Agent being taken over",
    )

    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        doc="True while human is actively handling the client",
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    handback_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Notes from human when returning control to AI",
    )

    # --- Relationships ---
    client: Mapped["ClientProfile"] = relationship(
        "ClientProfile",
        back_populates="human_takeovers",
    )

    def __repr__(self) -> str:
        return f"<HumanTakeover id={self.id} active={self.is_active}>"
