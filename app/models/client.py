"""
Client Profile Models

Tables:
- client_profiles     (client data, KYC, subscription info)
- credit_reports      (bureau reports)
- credit_report_snapshots  (historical score tracking)
- tradelines          (individual credit accounts)
- inquiries           (hard and soft inquiries)
- negative_items      (derogatory items)
"""
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey, Index,
    Integer, Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.agent import ClientAgentAssignment
    from app.models.dispute import DisputeCase
    from app.models.communication import CommunicationLog, ConsentLog
    from app.models.billing import Subscription, Purchase, Payment
    from app.models.appointment import Appointment, GroupSessionEnrollment
    from app.models.compliance import EscalationEvent, HumanTakeover
    from app.models.document import Document
    from app.models.audit import AuditTrail


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SubscriptionPlan(str, PyEnum):
    BASIC = "basic"        # $29.99/month
    PREMIUM = "premium"    # $79.99/month
    VIP = "vip"            # $199.99/month


class ClientStatus(str, PyEnum):
    ACTIVE = "active"
    PENDING_ONBOARDING = "pending_onboarding"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"
    CHURNED = "churned"


class BureauName(str, PyEnum):
    EQUIFAX = "equifax"
    EXPERIAN = "experian"
    TRANSUNION = "transunion"
    INNOVIS = "innovis"   # 4th bureau, optional


class TradelineStatus(str, PyEnum):
    CURRENT = "current"
    LATE_30 = "late_30"
    LATE_60 = "late_60"
    LATE_90 = "late_90"
    CHARGE_OFF = "charge_off"
    COLLECTION = "collection"
    PAID = "paid"
    CLOSED = "closed"
    TRANSFERRED = "transferred"
    DISPUTED = "disputed"


class DisputeOutcome(str, PyEnum):
    REMOVED = "removed"
    UPDATED = "updated"
    VERIFIED = "verified"
    REINVESTIGATION = "reinvestigation"
    PENDING = "pending"


# ---------------------------------------------------------------------------
# Client Profile
# ---------------------------------------------------------------------------

class ClientProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Client-specific data, separate from authentication (User table).
    
    PII handling:
    - SSN stored as last_4 digits only in this column
    - Full SSN encrypted at application layer, stored in separate encrypted column
    - DOB required for bureau API calls
    """
    __tablename__ = "client_profiles"

    # Link to auth
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Personal Information
    full_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    date_of_birth: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Required for credit bureau API calls",
    )
    ssn_last_4: Mapped[Optional[str]] = mapped_column(
        String(4),
        nullable=True,
        doc="Last 4 digits of SSN for display only",
    )
    ssn_encrypted: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Full SSN encrypted with AES-256 at application layer. For bureau API.",
    )

    # Contact Information
    phone: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        index=True,
    )
    phone_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # Address
    address_line1: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    zip_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="US")

    # Subscription
    subscription_plan: Mapped[Optional[SubscriptionPlan]] = mapped_column(
        Enum(SubscriptionPlan, name="subscription_plan_enum"),
        nullable=True,
    )
    subscription_status: Mapped[ClientStatus] = mapped_column(
        Enum(ClientStatus, name="client_status_enum"),
        nullable=False,
        default=ClientStatus.PENDING_ONBOARDING,
        index=True,
    )

    # Credit Score Tracking
    current_score_equifax: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_score_experian: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_score_transunion: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    score_goal: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Target credit score set by client",
    )
    score_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # KYC Verification
    identity_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    identity_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    identity_verification_provider: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="id.me, manual, stripe_identity",
    )

    # Stripe Customer
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        unique=True,
        index=True,
    )

    # Cancellation
    cancellation_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cancellation_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Three-Day Cancellation Right (CROA Compliance)
    three_day_right_expires: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="CROA: Client has 3 days from signup to cancel without penalty",
    )

    # Notes
    internal_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Admin-only internal notes about this client",
    )

    # --- Relationships ---
    user: Mapped["User"] = relationship(
        "User",
        back_populates="client_profile",
    )
    agent_assignments: Mapped[List["ClientAgentAssignment"]] = relationship(
        "ClientAgentAssignment",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    credit_reports: Mapped[List["CreditReport"]] = relationship(
        "CreditReport",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    credit_snapshots: Mapped[List["CreditReportSnapshot"]] = relationship(
        "CreditReportSnapshot",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    tradelines: Mapped[List["Tradeline"]] = relationship(
        "Tradeline",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    inquiries: Mapped[List["Inquiry"]] = relationship(
        "Inquiry",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    dispute_cases: Mapped[List["DisputeCase"]] = relationship(
        "DisputeCase",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    communication_logs: Mapped[List["CommunicationLog"]] = relationship(
        "CommunicationLog",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    consent_logs: Mapped[List["ConsentLog"]] = relationship(
        "ConsentLog",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    subscriptions: Mapped[List["Subscription"]] = relationship(
        "Subscription",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    purchases: Mapped[List["Purchase"]] = relationship(
        "Purchase",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    payments: Mapped[List["Payment"]] = relationship(
        "Payment",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    appointments: Mapped[List["Appointment"]] = relationship(
        "Appointment",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    session_enrollments: Mapped[List["GroupSessionEnrollment"]] = relationship(
        "GroupSessionEnrollment",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    escalation_events: Mapped[List["EscalationEvent"]] = relationship(
        "EscalationEvent",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    human_takeovers: Mapped[List["HumanTakeover"]] = relationship(
        "HumanTakeover",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    documents: Mapped[List["Document"]] = relationship(
        "Document",
        back_populates="client",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_client_profiles_status", "subscription_status"),
        Index("ix_client_profiles_stripe", "stripe_customer_id"),
    )

    def __repr__(self) -> str:
        return f"<ClientProfile id={self.id} name={self.full_name}>"


# ---------------------------------------------------------------------------
# Credit Reports
# ---------------------------------------------------------------------------

class CreditReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Full credit bureau report. Stored raw + parsed.
    One report per bureau pull per client.
    """
    __tablename__ = "credit_reports"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bureau: Mapped[BureauName] = mapped_column(
        Enum(BureauName, name="bureau_name_enum"),
        nullable=False,
        index=True,
    )
    pull_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    pull_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="full",
        doc="full, soft, monitoring",
    )

    # Score at time of pull
    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    score_model: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="FICO 8, VantageScore 3.0, etc.",
    )
    score_range_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    score_range_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Report data
    report_reference_number: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="Bureau's reference number for this pull",
    )
    raw_data_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        doc="S3 URL to encrypted raw report file",
    )
    parsed_data: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Parsed and normalized report data",
    )

    # Summary counts
    negative_items_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inquiries_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tradelines_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    collections_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # API Response
    api_response_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    api_error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Relationships ---
    client: Mapped[ClientProfile] = relationship(
        "ClientProfile",
        back_populates="credit_reports",
    )
    tradelines: Mapped[List["Tradeline"]] = relationship(
        "Tradeline",
        back_populates="report",
    )
    inquiries: Mapped[List["Inquiry"]] = relationship(
        "Inquiry",
        back_populates="report",
    )

    __table_args__ = (
        Index("ix_credit_reports_client_bureau_date", "client_id", "bureau", "pull_date"),
    )


# ---------------------------------------------------------------------------
# Credit Report Snapshots (Historical Score Tracking)
# ---------------------------------------------------------------------------

class CreditReportSnapshot(UUIDPrimaryKeyMixin, Base):
    """
    Monthly snapshots for score trend tracking.
    Lighter-weight than full report - just key metrics for dashboards.
    """
    __tablename__ = "credit_report_snapshots"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    score_equifax: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    score_experian: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    score_transunion: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    negative_items_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inquiries_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    collections_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_debt: Mapped[Optional[Numeric]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )
    utilization_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # --- Relationships ---
    client: Mapped[ClientProfile] = relationship(
        "ClientProfile",
        back_populates="credit_snapshots",
    )


# ---------------------------------------------------------------------------
# Tradelines (Individual Credit Accounts)
# ---------------------------------------------------------------------------

class Tradeline(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Individual account on a credit report.
    Each bureau pull may contain the same account reported separately.
    """
    __tablename__ = "tradelines"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    report_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("credit_reports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    bureau: Mapped[BureauName] = mapped_column(
        Enum(BureauName, name="bureau_name_enum2"),
        nullable=False,
    )

    # Account Details
    creditor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_number_masked: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="Masked account number (last 4 digits only)",
    )
    account_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="credit_card, auto_loan, mortgage, student_loan, personal_loan, collection",
    )

    # Financial
    balance: Mapped[Optional[Numeric]] = mapped_column(Numeric(12, 2), nullable=True)
    credit_limit: Mapped[Optional[Numeric]] = mapped_column(Numeric(12, 2), nullable=True)
    original_amount: Mapped[Optional[Numeric]] = mapped_column(Numeric(12, 2), nullable=True)
    monthly_payment: Mapped[Optional[Numeric]] = mapped_column(Numeric(10, 2), nullable=True)
    utilization: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Credit utilization percentage (0-100)",
    )

    # Status
    status: Mapped[TradelineStatus] = mapped_column(
        Enum(TradelineStatus, name="tradeline_status_enum"),
        nullable=False,
        default=TradelineStatus.CURRENT,
        index=True,
    )
    payment_history: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="24-month payment history: {'2026-01': 'OK', '2025-12': 'LATE_30'}",
    )

    # Dates
    date_opened: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    date_reported: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    date_last_active: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    date_closed: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Dispute Flags
    is_disputable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    dispute_reason: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        doc="Why this is disputable: inaccurate, obsolete, unverifiable",
    )
    analyst_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Relationships ---
    client: Mapped[ClientProfile] = relationship(
        "ClientProfile",
        back_populates="tradelines",
    )
    report: Mapped[Optional[CreditReport]] = relationship(
        "CreditReport",
        back_populates="tradelines",
    )

    __table_args__ = (
        Index("ix_tradelines_client_status", "client_id", "status"),
        Index("ix_tradelines_disputable", "client_id", "is_disputable"),
    )


# ---------------------------------------------------------------------------
# Inquiries
# ---------------------------------------------------------------------------

class Inquiry(UUIDPrimaryKeyMixin, Base):
    """
    Hard and soft inquiries on credit report.
    Hard inquiries impact score; soft don't.
    """
    __tablename__ = "inquiries"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    report_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("credit_reports.id", ondelete="SET NULL"),
        nullable=True,
    )
    bureau: Mapped[BureauName] = mapped_column(
        Enum(BureauName, name="bureau_name_enum3"),
        nullable=False,
    )
    inquirer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    inquiry_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    is_hard_inquiry: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    is_disputable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="True if client did not authorize this inquiry",
    )
    is_duplicate: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # --- Relationships ---
    client: Mapped[ClientProfile] = relationship(
        "ClientProfile",
        back_populates="inquiries",
    )
    report: Mapped[Optional[CreditReport]] = relationship(
        "CreditReport",
        back_populates="inquiries",
    )
