"""
Agent Profile Models

Tables:
- agent_profiles            (AI agent configuration, personality, permissions)
- client_agent_assignments  (which client is assigned to which agent)
- agent_activity_logs       (tracks agent actions for performance monitoring)
"""
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index,
    Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.client import ClientProfile
    from app.models.dispute import DisputeCase, DisputeLetter
    from app.models.communication import CommunicationLog
    from app.models.audit import AuditTrail


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AgentRole(str, PyEnum):
    CLIENT_SUCCESS = "client_success"      # Tim Shaw - the face clients see
    CREDIT_ANALYST = "credit_analyst"      # Analyzes reports, identifies disputes
    COMPLIANCE_ENGINE = "compliance_engine"  # Reviews all outbound communication
    SCHEDULER = "scheduler"               # Manages appointments & timing
    RECOMMENDATION = "recommendation"     # Product & action recommendations
    SUPERVISOR = "supervisor"             # Human oversight coordination


class AgentStatus(str, PyEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"   # Permanently decommissioned, preserved for audit


class VoiceProvider(str, PyEnum):
    ELEVENLABS = "elevenlabs"
    GOOGLE_TTS = "google_tts"
    TWILIO = "twilio"


class AvatarType(str, PyEnum):
    TAVUS = "tavus"           # AI video avatar
    STATIC_IMAGE = "static"   # Static photo
    CUSTOM_VIDEO = "custom"   # Pre-recorded video


# ---------------------------------------------------------------------------
# Agent Profile (Main Table)
# ---------------------------------------------------------------------------

class AgentProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    AI Agent configuration. Each profile defines a distinct agent persona.
    
    Tim Shaw is the primary client-facing agent. Additional agents (Maria Garcia,
    Detective Dave, etc.) can be created by admin and assigned to clients.
    
    Permissions stored as JSON allow fine-grained control without schema changes.
    """
    __tablename__ = "agent_profiles"

    # Identity
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Agent's display name (e.g., 'Tim Shaw')",
    )
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        doc="Functional role of this agent in the system",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="active",
        index=True,
    )

    # Personality & Tone
    personality_prompt: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="System prompt defining agent's personality, tone, and communication style",
    )
    greeting_template: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Default greeting message template",
    )
    closing_template: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    tone_descriptor: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        doc="Short description: 'calm, professional, confident'",
    )

    # Specialties
    specialties: Mapped[Optional[List]] = mapped_column(
        JSON,
        nullable=True,
        doc="List of specialty areas: ['credit_disputes', 'financial_education']",
    )

    # Knowledge Base Configuration
    knowledge_base_config: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="What knowledge domains this agent has access to",
    )

    # Voice Settings
    voice_provider: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    voice_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        doc="Provider-specific voice ID (e.g., ElevenLabs voice_id)",
    )
    voice_settings: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="JSON: speech_rate, pitch, language, tone settings",
    )

    # Avatar / Video Settings
    avatar_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    avatar_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        doc="Provider-specific avatar identifier",
    )
    avatar_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        doc="URL to static avatar image",
    )
    avatar_settings: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="JSON: appearance, preset, disclosure_overlay settings",
    )

    # Permissions
    permissions: Mapped[Dict] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: {
            "can_answer_faqs": True,
            "can_file_disputes": False,          # Requires human approval
            "can_recommend_products": False,      # Requires compliance check
            "can_schedule_meetings": True,
            "can_escalate": True,
            "can_access_documents": False,
            "can_send_sms": False,
            "can_make_calls": False,
            "can_send_email": False,
            "can_initiate_video": False,
            "requires_human_approval_for_disputes": True,
        },
        doc="Granular permission flags. Admin controls all permissions.",
    )

    # Capacity
    max_clients: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=2000,
        doc="Maximum number of concurrent client assignments",
    )

    # Performance Metrics (denormalized for fast dashboard queries)
    total_clients_assigned: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    total_messages_sent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    avg_response_time_minutes: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    avg_satisfaction_rating: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Average client satisfaction rating (1.0-5.0)",
    )
    compliance_violations_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Soft deactivation
    deactivated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deactivated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        doc="Admin user who deactivated this agent",
    )

    # --- Relationships ---
    client_assignments: Mapped[List["ClientAgentAssignment"]] = relationship(
        "ClientAgentAssignment",
        back_populates="agent",
        cascade="all, delete-orphan",
    )
    activity_logs: Mapped[List["AgentActivityLog"]] = relationship(
        "AgentActivityLog",
        back_populates="agent",
        cascade="all, delete-orphan",
    )
    dispute_cases: Mapped[List["DisputeCase"]] = relationship(
        "DisputeCase",
        back_populates="filing_agent",
    )
    dispute_letters: Mapped[List["DisputeLetter"]] = relationship(
        "DisputeLetter",
        back_populates="drafting_agent",
    )
    communication_logs: Mapped[List["CommunicationLog"]] = relationship(
        "CommunicationLog",
        back_populates="agent",
    )

    __table_args__ = (
        Index("ix_agent_profiles_role_status", "role", "status"),
    )

    def __repr__(self) -> str:
        return f"<AgentProfile id={self.id} name={self.name} role={self.role}>"

    @property
    def is_at_capacity(self) -> bool:
        """Check if agent has reached maximum client load."""
        return self.total_clients_assigned >= self.max_clients

    @property
    def current_load_percentage(self) -> float:
        """Return current load as percentage of max capacity."""
        if self.max_clients == 0:
            return 100.0
        return (self.total_clients_assigned / self.max_clients) * 100


# ---------------------------------------------------------------------------
# Client-Agent Assignment
# ---------------------------------------------------------------------------

class ClientAgentAssignment(UUIDPrimaryKeyMixin, Base):
    """
    Tracks which agent is assigned to which client, with full history.
    
    When an agent is reassigned:
    1. Current assignment's unassigned_at is set
    2. New assignment record is created
    Full history preserved for audit trail.
    """
    __tablename__ = "client_agent_assignments"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    unassigned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When this assignment ended. Null = currently active.",
    )
    reason_for_assignment: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        doc="Why this agent was selected: auto_assigned, admin_selected, load_balance",
    )
    reason_for_change: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        doc="Why assignment changed: client_request, agent_deactivated, rebalance",
    )
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        doc="Admin user who made the change",
    )

    # --- Relationships ---
    client: Mapped["ClientProfile"] = relationship(
        "ClientProfile",
        back_populates="agent_assignments",
    )
    agent: Mapped[AgentProfile] = relationship(
        "AgentProfile",
        back_populates="client_assignments",
    )

    __table_args__ = (
        # Only one active assignment per client at a time
        Index(
            "ix_active_client_assignment",
            "client_id",
            postgresql_where="unassigned_at IS NULL",
        ),
        Index("ix_assignments_agent_client", "agent_id", "client_id"),
    )

    @property
    def is_active(self) -> bool:
        return self.unassigned_at is None

    def __repr__(self) -> str:
        return (
            f"<ClientAgentAssignment "
            f"client={self.client_id} "
            f"agent={self.agent_id} "
            f"active={self.is_active}>"
        )


# ---------------------------------------------------------------------------
# Agent Activity Log (Performance Tracking)
# ---------------------------------------------------------------------------

class AgentActivityLog(UUIDPrimaryKeyMixin, Base):
    """
    Records individual agent actions for performance monitoring and auditing.
    High-volume table - consider partitioning by month in production.
    """
    __tablename__ = "agent_activity_logs"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        doc="message_sent, dispute_filed, recommendation_made, escalation_triggered",
    )
    action_detail: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        nullable=True,
    )
    channel: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="sms, email, call, chat, video",
    )
    compliance_checked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    compliance_passed: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
    )
    human_approved: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # --- Relationships ---
    agent: Mapped[AgentProfile] = relationship(
        "AgentProfile",
        back_populates="activity_logs",
    )

    __table_args__ = (
        Index("ix_activity_logs_agent_time", "agent_id", "occurred_at"),
        Index("ix_activity_logs_client_time", "client_id", "occurred_at"),
    )
