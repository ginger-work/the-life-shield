"""
The Life Shield — SQLAlchemy Models

Import all models here so Alembic autogenerate and init_db can discover them.
"""

from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.user import User, UserRole, UserStatus
from app.models.agent import (
    AgentProfile,
    AgentRole,
    AgentStatus,
    ClientAgentAssignment,
    AgentActivityLog,
)
from app.models.client import (
    ClientProfile,
    CreditReport,
    CreditReportSnapshot,
    Tradeline,
    Inquiry,
    SubscriptionPlan,
    ClientStatus,
    BureauName,
    TradelineStatus,
)
from app.models.dispute import (
    DisputeCase,
    DisputeLetter,
    BureauResponse,
    DisputeStatus,
    DisputeReason,
    BureauResponseType,
    LetterStatus,
)
from app.models.communication import (
    CommunicationLog,
    ConsentLog,
)
from app.models.billing import (
    Subscription,
    Purchase,
    Payment,
)
from app.models.audit import AuditTrail, AuditAction
from app.models.compliance import (
    EscalationEvent,
    HumanTakeover,
    EscalationReason,
    EscalationStatus,
)
from app.models.document import Document, DocumentType
from app.models.appointment import (
    Appointment,
    GroupSession,
    GroupSessionEnrollment,
    AppointmentStatus,
    AppointmentType,
)

__all__ = [
    # Base
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    # User
    "User",
    "UserRole",
    "UserStatus",
    # Agent
    "AgentProfile",
    "AgentRole",
    "AgentStatus",
    "ClientAgentAssignment",
    "AgentActivityLog",
    # Client
    "ClientProfile",
    "CreditReport",
    "CreditReportSnapshot",
    "Tradeline",
    "Inquiry",
    "SubscriptionPlan",
    "ClientStatus",
    "BureauName",
    "TradelineStatus",
    # Dispute
    "DisputeCase",
    "DisputeLetter",
    "BureauResponse",
    "DisputeStatus",
    "DisputeReason",
    "BureauResponseType",
    "LetterStatus",
    # Communication
    "CommunicationLog",
    "ConsentLog",
    # Billing
    "Subscription",
    "Purchase",
    "Payment",
    # Audit
    "AuditTrail",
    "AuditAction",
    # Compliance
    "EscalationEvent",
    "HumanTakeover",
    "EscalationReason",
    "EscalationStatus",
    # Document
    "Document",
    "DocumentType",
    # Appointment
    "Appointment",
    "GroupSession",
    "GroupSessionEnrollment",
    "AppointmentStatus",
    "AppointmentType",
]
