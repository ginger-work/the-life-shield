"""
Communication Models

Tables:
- communication_logs        (all messages, calls, emails - unified log)
- consent_logs              (who consented to what channel, when)
- disclosure_logs           (signed disclosures: AI, service agreement, etc.)
- opt_out_requests          (honored immediately, logged immutably)
"""
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Index,
    Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.client import ClientProfile
    from app.models.agent import AgentProfile


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CommunicationChannel(str, PyEnum):
    SMS = "sms"
    EMAIL = "email"
    VOICE_CALL = "voice_call"
    PORTAL_CHAT = "portal_chat"
    VIDEO = "video"
    SYSTEM = "system"   # Internal system notifications


class CommunicationDirection(str, PyEnum):
    INBOUND = "inbound"    # Client → System
    OUTBOUND = "outbound"  # System → Client


class CommunicationStatus(str, PyEnum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    BLOCKED = "blocked"    # Blocked by compliance check
    BOUNCED = "bounced"


class ConsentType(str, PyEnum):
    SMS = "sms"
    VOICE_CALL = "voice_call"
    EMAIL = "email"
    VIDEO_CALL = "video_call"
    CALL_RECORDING = "call_recording"
    VIDEO_RECORDING = "video_recording"
    AI_DISCLOSURE = "ai_disclosure"
    SERVICE_AGREEMENT = "service_agreement"
    TERMS_OF_SERVICE = "terms_of_service"
    PRIVACY_POLICY = "privacy_policy"
    MARKETING_EMAIL = "marketing_email"


class DisclosureType(str, PyEnum):
    SERVICE_AGREEMENT = "service_agreement"
    AI_DISCLOSURE = "ai_disclosure"
    CANCELLATION_RIGHTS = "cancellation_rights"   # 3-day CROA right
    CROA_DISCLOSURE = "croa_disclosure"
    FCRA_DISCLOSURE = "fcra_disclosure"
    PRIVACY_POLICY = "privacy_policy"
    TERMS_OF_SERVICE = "terms_of_service"
    CALL_RECORDING = "call_recording"


# ---------------------------------------------------------------------------
# Communication Log (Unified)
# ---------------------------------------------------------------------------

class CommunicationLog(UUIDPrimaryKeyMixin, Base):
    """
    Immutable log of every communication event.
    
    This is a compliance-critical table:
    - Never update or delete records
    - All communications must be logged (per FCRA audit requirements)
    - Consent reference links each message to its consent record
    
    High volume: consider partitioning by month in production.
    """
    __tablename__ = "communication_logs"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Communication Details
    channel: Mapped[CommunicationChannel] = mapped_column(
        Enum(CommunicationChannel, name="comm_channel_enum"),
        nullable=False,
        index=True,
    )
    direction: Mapped[CommunicationDirection] = mapped_column(
        Enum(CommunicationDirection, name="comm_direction_enum"),
        nullable=False,
        index=True,
    )
    status: Mapped[CommunicationStatus] = mapped_column(
        Enum(CommunicationStatus, name="comm_status_enum"),
        nullable=False,
        default=CommunicationStatus.SENT,
        index=True,
    )

    # Content
    message_content: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Message text (SMS, email body, chat message)",
    )
    message_subject: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        doc="Email subject line",
    )

    # Voice/Video Specifics
    call_duration_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    call_recording_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        doc="S3 URL to call recording (only if consent granted)",
    )
    call_transcription: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    call_sid: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="Twilio Call SID for voice calls",
    )
    message_sid: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="Twilio Message SID for SMS",
    )

    # Email Specifics
    email_message_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        doc="SendGrid message ID",
    )

    # Compliance
    compliance_checked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    compliance_passed: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
    )
    compliance_flags: Mapped[Optional[List]] = mapped_column(
        JSON,
        nullable=True,
    )
    flagged_for_review: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    consent_reference_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        doc="FK to consent_logs record that authorized this communication",
    )

    # Metadata
    external_ref: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        doc="External reference (Twilio, SendGrid ID)",
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    extra_data: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        nullable=True,
    )

    # Timestamp
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # --- Relationships ---
    client: Mapped["ClientProfile"] = relationship(
        "ClientProfile",
        back_populates="communication_logs",
    )
    agent: Mapped[Optional["AgentProfile"]] = relationship(
        "AgentProfile",
        back_populates="communication_logs",
    )

    __table_args__ = (
        Index("ix_comm_logs_client_channel", "client_id", "channel"),
        Index("ix_comm_logs_client_time", "client_id", "occurred_at"),
        Index("ix_comm_logs_compliance_flagged", "flagged_for_review", "compliance_passed"),
    )

    def __repr__(self) -> str:
        return (
            f"<CommunicationLog id={self.id} "
            f"channel={self.channel} "
            f"direction={self.direction}>"
        )


# ---------------------------------------------------------------------------
# Consent Logs (Immutable)
# ---------------------------------------------------------------------------

class ConsentLog(UUIDPrimaryKeyMixin, Base):
    """
    CRITICAL compliance table. Records every consent grant and revocation.
    
    Rules:
    - Records are immutable (never UPDATE or DELETE)
    - Revocation adds a new record, doesn't modify the grant
    - Every communication must reference a consent record
    - Proof of consent must be stored (how consent was given)
    
    Per FCC/TCPA: Prior express written consent required for SMS/calls.
    """
    __tablename__ = "consent_logs"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    consent_type: Mapped[ConsentType] = mapped_column(
        Enum(ConsentType, name="consent_type_enum"),
        nullable=False,
        index=True,
    )

    # Grant or Revocation
    is_granted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        doc="True = consent granted, False = consent revoked",
    )
    action_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # How consent was given
    method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="signup_form",
        doc="signup_form, verbal, written, portal_settings, stop_reply",
    )
    proof_of_consent: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Signature, checkbox state, IP address, timestamp, form version",
    )

    # Revocation Details
    revocation_method: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="stop_sms, unsubscribe_email, portal_settings, verbal_request, legal",
    )
    revocation_keyword: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="STOP, UNSUBSCRIBE, CANCEL, QUIT, HELP, etc.",
    )

    # IP & Agent
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    form_version: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        doc="Version of signup form where consent was collected",
    )

    # --- Relationships ---
    client: Mapped["ClientProfile"] = relationship(
        "ClientProfile",
        back_populates="consent_logs",
    )

    __table_args__ = (
        Index("ix_consent_logs_client_type", "client_id", "consent_type"),
        Index("ix_consent_logs_client_action", "client_id", "action_date"),
    )

    def __repr__(self) -> str:
        action = "GRANTED" if self.is_granted else "REVOKED"
        return f"<ConsentLog id={self.id} type={self.consent_type} {action}>"


# ---------------------------------------------------------------------------
# Disclosure Logs (Signed Disclosures)
# ---------------------------------------------------------------------------

class DisclosureLog(UUIDPrimaryKeyMixin, Base):
    """
    Records when client signed specific disclosures.
    Required by CROA: service agreement must be signed before payment.
    Required by FTC: AI must be disclosed on video.
    """
    __tablename__ = "disclosure_logs"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    disclosure_type: Mapped[DisclosureType] = mapped_column(
        Enum(DisclosureType, name="disclosure_type_enum"),
        nullable=False,
        index=True,
    )
    signed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    content_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="Version of the disclosure document",
    )
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        doc="SHA-256 hash of disclosure content at time of signing",
    )
    signature_data: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="IP address, user-agent, timestamp, electronic signature",
    )
    delivery_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="portal_signup",
        doc="portal_signup, email, paper, verbal",
    )

    __table_args__ = (
        Index("ix_disclosure_logs_client_type", "client_id", "disclosure_type"),
    )


# ---------------------------------------------------------------------------
# Opt-Out Requests (Honored Immediately, Per Spec)
# ---------------------------------------------------------------------------

class OptOutRequest(UUIDPrimaryKeyMixin, Base):
    """
    Records every opt-out request.
    System must honor immediately (within seconds, not days).
    Logging here creates the audit trail proving compliance.
    """
    __tablename__ = "opt_out_requests"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="Which channel they opted out of (null = all channels)",
    )
    trigger_keyword: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="STOP, UNSUBSCRIBE, etc.",
    )
    trigger_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Full message that triggered opt-out",
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    honored_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When system confirmed opt-out was processed",
    )
    supervisor_notified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    __table_args__ = (
        Index("ix_opt_out_client_time", "client_id", "requested_at"),
    )
