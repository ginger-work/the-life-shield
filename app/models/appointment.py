"""
Appointment & Group Session Models

Tables:
- appointments          (1-on-1 client appointments)
- group_sessions        (group education sessions)
- group_session_enrollments
"""
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.client import ClientProfile
    from app.models.user import User


class AppointmentStatus(str, PyEnum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    RESCHEDULED = "rescheduled"


class AppointmentType(str, PyEnum):
    ONBOARDING = "onboarding"
    CREDIT_REVIEW = "credit_review"
    DISPUTE_REVIEW = "dispute_review"
    PROGRESS_UPDATE = "progress_update"
    GOAL_SETTING = "goal_setting"
    FOLLOWUP = "followup"


class Appointment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Client 1-on-1 appointment with a human specialist."""
    __tablename__ = "appointments"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    specialist_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    appointment_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="scheduled",
        index=True,
    )

    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    duration_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30,
    )
    meeting_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Relationships ---
    client: Mapped["ClientProfile"] = relationship(
        "ClientProfile",
        back_populates="appointments",
    )

    def __repr__(self) -> str:
        return f"<Appointment id={self.id} type={self.appointment_type} at={self.scheduled_at}>"


class GroupSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Group education/webinar sessions."""
    __tablename__ = "group_sessions"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    session_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="webinar, workshop, qa_session",
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    max_attendees: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    meeting_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    recording_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    enrollments: Mapped[List["GroupSessionEnrollment"]] = relationship(
        "GroupSessionEnrollment",
        back_populates="session",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<GroupSession id={self.id} title={self.title!r}>"


class GroupSessionEnrollment(UUIDPrimaryKeyMixin, Base):
    """Enrollment record linking a client to a group session."""
    __tablename__ = "group_session_enrollments"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("group_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    attended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- Relationships ---
    client: Mapped["ClientProfile"] = relationship(
        "ClientProfile",
        back_populates="session_enrollments",
    )
    session: Mapped[GroupSession] = relationship(
        "GroupSession",
        back_populates="enrollments",
    )

    def __repr__(self) -> str:
        return f"<GroupSessionEnrollment client={self.client_id} session={self.session_id}>"
