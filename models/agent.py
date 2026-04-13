"""
The Life Shield - Agent Profile Model
SQLAlchemy ORM model for AI agent profiles and client-agent assignments.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Enum as SAEnum, Float,
    ForeignKey, Integer, String, Text, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

from .base import Base


# ─────────────────────────────────────────────
# AGENT PROFILE
# ─────────────────────────────────────────────

class AgentProfile(Base):
    """
    AI agent identity and configuration.
    Admins create and manage agents; clients are assigned to agents.
    Corresponds to "Tim Shaw" persona in the spec.
    """
    __tablename__ = "agent_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Identity (links to users table — agents have user accounts)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True
    )

    # Agent persona
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)  # "Tim Shaw"
    role: Mapped[str] = mapped_column(
        String(50), nullable=False, default="client_success_agent"
    )
    # Roles: client_success_agent, credit_analyst, compliance_agent,
    #        scheduler, recommendation_agent, supervisor

    # Personality & tone
    tone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    communication_style: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    greeting_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    closing_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Voice configuration
    voice_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # elevenlabs, google_tts
    voice_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    speech_rate: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    pitch: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    # Avatar configuration
    avatar_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # tavus, custom
    avatar_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    disclosure_text: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="AI Client Agent for The Life Shield"
    )

    # Specialties (JSON list of skill areas)
    specialties: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Knowledge base flags
    knows_fcra: Mapped[bool] = mapped_column(Boolean, default=True)
    knows_croa: Mapped[bool] = mapped_column(Boolean, default=True)
    knows_fcc_rules: Mapped[bool] = mapped_column(Boolean, default=True)
    knows_nc_regulations: Mapped[bool] = mapped_column(Boolean, default=True)

    # Permissions (granular flags per spec)
    can_answer_faq: Mapped[bool] = mapped_column(Boolean, default=True)
    can_explain_status: Mapped[bool] = mapped_column(Boolean, default=True)
    can_schedule_meetings: Mapped[bool] = mapped_column(Boolean, default=True)
    can_send_reminders: Mapped[bool] = mapped_column(Boolean, default=True)
    can_gather_documents: Mapped[bool] = mapped_column(Boolean, default=True)
    can_recommend_products: Mapped[bool] = mapped_column(Boolean, default=False)
    can_file_disputes: Mapped[bool] = mapped_column(Boolean, default=False)
    can_make_promises: Mapped[bool] = mapped_column(Boolean, default=False)  # ALWAYS FALSE
    can_escalate: Mapped[bool] = mapped_column(Boolean, default=True)
    can_override_decisions: Mapped[bool] = mapped_column(Boolean, default=False)  # HUMANS ONLY

    # Capacity & performance
    max_clients: Mapped[int] = mapped_column(Integer, default=2000)
    performance_rating: Mapped[float] = mapped_column(Float, default=0.0)
    satisfaction_score: Mapped[float] = mapped_column(Float, default=0.0)
    compliance_violations: Mapped[int] = mapped_column(Integer, default=0)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_accepting_clients: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False
    )
    active_since: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    client_assignments = relationship(
        "ClientAgentAssignment", back_populates="agent", cascade="all, delete-orphan"
    )

    @property
    def assigned_client_count(self) -> int:
        return len([a for a in self.client_assignments if a.is_active])

    def __repr__(self) -> str:
        return f"<AgentProfile id={self.id} name={self.display_name} role={self.role}>"


# ─────────────────────────────────────────────
# CLIENT-AGENT ASSIGNMENT
# ─────────────────────────────────────────────

class ClientAgentAssignment(Base):
    """
    Maps a client user to their assigned AI agent.
    One active assignment per client at a time.
    """
    __tablename__ = "client_agent_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_profiles.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reassigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    agent = relationship("AgentProfile", back_populates="client_assignments")
    client = relationship("User", foreign_keys=[client_user_id])
    assigned_by = relationship("User", foreign_keys=[assigned_by_user_id])

    def __repr__(self) -> str:
        return f"<ClientAgentAssignment client={self.client_user_id} agent={self.agent_id}>"
