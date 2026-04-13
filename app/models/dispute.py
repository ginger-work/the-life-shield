"""
Dispute Models

Tables:
- dispute_cases     (active and historical disputes)
- dispute_letters   (content, approval workflow)
- bureau_responses  (investigation outcomes)
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


class DisputeStatus(str, PyEnum):
    PENDING_APPROVAL = "pending_approval"    # Waiting for human approval
    APPROVED = "approved"                    # Ready to file
    PENDING_FILING = "pending_filing"        # About to be submitted
    FILED = "filed"                          # Submitted to bureau
    INVESTIGATING = "investigating"          # Bureau is investigating (30 days)
    RESPONDED = "responded"                  # Bureau replied
    RESOLVED = "resolved"                    # Case closed
    REJECTED = "rejected"                    # Admin rejected the letter
    WITHDRAWN = "withdrawn"                  # Client or admin withdrew


class DisputeReason(str, PyEnum):
    INACCURATE = "inaccurate"
    INCOMPLETE = "incomplete"
    UNVERIFIABLE = "unverifiable"
    OBSOLETE = "obsolete"              # Past 7-year reporting limit
    FRAUDULENT = "fraudulent"          # Identity theft
    NOT_MINE = "not_mine"             # Account doesn't belong to client
    WRONG_BALANCE = "wrong_balance"
    WRONG_STATUS = "wrong_status"
    DUPLICATE = "duplicate"


class BureauResponseType(str, PyEnum):
    REMOVED = "removed"
    UPDATED = "updated"
    VERIFIED = "verified"           # Bureau confirmed item is accurate
    REINVESTIGATION = "reinvestigation"  # Bureau needs more time
    DELETED = "deleted"             # Same as removed, different terminology
    NO_RESPONSE = "no_response"     # Bureau didn't respond in 30 days (violation)


class LetterStatus(str, PyEnum):
    DRAFT = "draft"
    PENDING_COMPLIANCE = "pending_compliance"
    PENDING_HUMAN_APPROVAL = "pending_human_approval"
    APPROVED = "approved"
    REVISION_REQUESTED = "revision_requested"
    FILED = "filed"
    ARCHIVED = "archived"


# ---------------------------------------------------------------------------
# Dispute Cases
# ---------------------------------------------------------------------------

class DisputeCase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    A dispute case represents one item being challenged at one bureau.
    
    Approval workflow:
    1. Credit analyst identifies disputable item
    2. Compliance engine checks language
    3. Human admin approves (mandatory per spec)
    4. System files to bureau
    5. Bureau has 30 days to respond (FCRA)
    6. System logs outcome
    """
    __tablename__ = "dispute_cases"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filing_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tradeline_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tradelines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Dispute Details
    bureau: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        doc="equifax, experian, transunion",
    )
    dispute_reason: Mapped[DisputeReason] = mapped_column(
        Enum(DisputeReason, name="dispute_reason_enum"),
        nullable=False,
    )
    item_description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Human-readable description of what is being disputed",
    )
    creditor_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    account_number_masked: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )

    # Status & Timeline
    status: Mapped[DisputeStatus] = mapped_column(
        Enum(DisputeStatus, name="dispute_status_enum"),
        nullable=False,
        default=DisputeStatus.PENDING_APPROVAL,
        index=True,
    )
    filed_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expected_response_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="30 days from filing date per FCRA",
    )
    response_received_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Outcome
    outcome: Mapped[Optional[BureauResponseType]] = mapped_column(
        Enum(BureauResponseType, name="bureau_response_type_enum"),
        nullable=True,
    )
    outcome_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    score_impact_points: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Estimated or actual score change from this dispute outcome",
    )

    # Filing Proof
    dispute_letter_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        doc="S3 URL to the submitted dispute letter",
    )
    proof_of_filing_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        doc="S3 URL to proof of submission (certified mail, API confirmation)",
    )

    # Priority
    priority_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
        doc="1-10 priority score from analyst (higher = more impactful)",
    )

    # Metadata
    analyst_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Relationships ---
    client: Mapped["ClientProfile"] = relationship(
        "ClientProfile",
        back_populates="dispute_cases",
    )
    filing_agent: Mapped[Optional["AgentProfile"]] = relationship(
        "AgentProfile",
        back_populates="dispute_cases",
    )
    letters: Mapped[List["DisputeLetter"]] = relationship(
        "DisputeLetter",
        back_populates="dispute",
        cascade="all, delete-orphan",
    )
    bureau_responses: Mapped[List["BureauResponse"]] = relationship(
        "BureauResponse",
        back_populates="dispute",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_dispute_cases_client_status", "client_id", "status"),
        Index("ix_dispute_cases_bureau_status", "bureau", "status"),
        Index("ix_dispute_cases_filed_date", "filed_date"),
    )

    def __repr__(self) -> str:
        return f"<DisputeCase id={self.id} bureau={self.bureau} status={self.status}>"


# ---------------------------------------------------------------------------
# Dispute Letters
# ---------------------------------------------------------------------------

class DisputeLetter(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    The actual letter content for a dispute filing.
    
    Approval workflow per spec:
    - AI drafts letter
    - Compliance engine checks for FCRA/CROA violations
    - Human admin must approve before filing
    """
    __tablename__ = "dispute_letters"

    dispute_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dispute_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    drafting_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Letter Content
    letter_content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Full dispute letter text",
    )
    letter_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        doc="Version number (increments on revision)",
    )

    # Compliance Review
    compliance_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        doc="pending, passed, flagged",
    )
    compliance_checked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    compliance_flags: Mapped[Optional[List]] = mapped_column(
        JSON,
        nullable=True,
        doc="List of compliance issues found",
    )

    # Human Approval
    human_approval_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        doc="Always true per spec - disputes require human approval",
    )
    approved_by_admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        doc="Admin user ID who approved this letter",
    )
    approval_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Status
    status: Mapped[LetterStatus] = mapped_column(
        Enum(LetterStatus, name="letter_status_enum"),
        nullable=False,
        default=LetterStatus.DRAFT,
        index=True,
    )

    # AI Generation Metadata
    ai_model_used: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="Which AI model generated this draft",
    )
    generation_prompt_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        doc="SHA-256 hash of the generation prompt (for reproducibility)",
    )

    # --- Relationships ---
    dispute: Mapped[DisputeCase] = relationship(
        "DisputeCase",
        back_populates="letters",
    )
    drafting_agent: Mapped[Optional["AgentProfile"]] = relationship(
        "AgentProfile",
        back_populates="dispute_letters",
    )

    __table_args__ = (
        Index("ix_dispute_letters_status", "status"),
        Index("ix_dispute_letters_compliance", "compliance_status"),
    )


# ---------------------------------------------------------------------------
# Bureau Responses
# ---------------------------------------------------------------------------

class BureauResponse(UUIDPrimaryKeyMixin, Base):
    """
    Records the bureau's response to a dispute investigation.
    Outcome feeds back into the dispute case and client's credit record.
    """
    __tablename__ = "bureau_responses"

    dispute_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dispute_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    received_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    response_type: Mapped[BureauResponseType] = mapped_column(
        Enum(BureauResponseType, name="bureau_response_type_enum2"),
        nullable=False,
    )
    response_content: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Full text of bureau's response letter",
    )
    response_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        doc="S3 URL to scanned response document",
    )
    score_impact: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Score points changed as a result of this response",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # --- Relationships ---
    dispute: Mapped[DisputeCase] = relationship(
        "DisputeCase",
        back_populates="bureau_responses",
    )

    def __repr__(self) -> str:
        return f"<BureauResponse id={self.id} type={self.response_type}>"
