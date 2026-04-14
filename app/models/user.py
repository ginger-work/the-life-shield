"""
User & Authentication Models

Tables:
- users                  (authentication, role-based access)
- failed_login_attempts  (security monitoring, account lockout)
- password_reset_tokens  (secure password reset flow)
- refresh_tokens         (JWT refresh token tracking + revocation)
"""
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.client import ClientProfile
    from app.models.audit import AuditTrail


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class UserRole(str, PyEnum):
    ADMIN = "admin"          # Full back-office access
    STAFF = "staff"          # Limited back-office (compliance, support)
    CLIENT = "client"        # Portal access only
    AGENT = "agent"          # AI agent service account (internal)


class UserStatus(str, PyEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"  # Temporary suspension (policy violation)
    PENDING_VERIFICATION = "pending_verification"  # Email not yet verified


# ---------------------------------------------------------------------------
# Users Table (Authentication Core)
# ---------------------------------------------------------------------------

class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Core authentication table. Stores credentials and role.
    
    Design principles:
    - Passwords hashed with bcrypt (never stored plaintext)
    - Email is case-insensitive (stored lowercase, use citext in migration)
    - Role determines access level across entire system
    - SSN and sensitive PII is NOT stored here - see ClientProfile
    """
    __tablename__ = "users"

    # Credentials
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        doc="User's email address (unique, case-insensitive login)",
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="bcrypt-hashed password. Never store plaintext.",
    )

    # Identity
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="client",
        index=True,
        doc="Role determines what this user can access",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending_verification",
        index=True,
    )

    # Verification
    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    email_verification_token: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    # Security tracking
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_login_ip: Mapped[Optional[str]] = mapped_column(
        String(45),  # IPv6 max length
        nullable=True,
    )
    login_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    is_locked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="True when account is locked due to failed login attempts",
    )
    locked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # MFA (Phase 2)
    mfa_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    mfa_secret: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # Soft delete
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="If set, user is soft-deleted. Never hard-delete users.",
    )

    # --- Relationships ---
    client_profile: Mapped[Optional["ClientProfile"]] = relationship(
        "ClientProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    failed_login_attempts: Mapped[List["FailedLoginAttempt"]] = relationship(
        "FailedLoginAttempt",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    password_reset_tokens: Mapped[List["PasswordResetToken"]] = relationship(
        "PasswordResetToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    # audit_entries relationship removed — use audit_service.get_client_audit_log() instead

    # --- Indexes ---
    __table_args__ = (
        Index("ix_users_email_lower", func.lower(email)),
        Index("ix_users_role_status", "role", "status"),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"


# ---------------------------------------------------------------------------
# Failed Login Attempts (Security Monitoring)
# ---------------------------------------------------------------------------

class FailedLoginAttempt(UUIDPrimaryKeyMixin, Base):
    """
    Records every failed login attempt for security monitoring and lockout.
    Retained for 90 days for audit purposes.
    """
    __tablename__ = "failed_login_attempts"

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="User ID if account found (null if email not found)",
    )
    attempted_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        doc="Email used in the failed attempt",
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    failure_reason: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="invalid_credentials",
        doc="Why login failed: invalid_credentials, account_locked, etc.",
    )
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # --- Relationships ---
    user: Mapped[Optional[User]] = relationship(
        "User",
        back_populates="failed_login_attempts",
    )

    __table_args__ = (
        Index("ix_failed_logins_user_time", "user_id", "attempted_at"),
        Index("ix_failed_logins_ip_time", "ip_address", "attempted_at"),
    )


# ---------------------------------------------------------------------------
# Password Reset Tokens
# ---------------------------------------------------------------------------

class PasswordResetToken(UUIDPrimaryKeyMixin, Base):
    """
    Single-use tokens for password reset flow.
    Tokens expire after 1 hour.
    """
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        doc="SHA-256 hash of the reset token (never store raw token)",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp when token was consumed. Single-use only.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    # --- Relationships ---
    user: Mapped[User] = relationship(
        "User",
        back_populates="password_reset_tokens",
    )


# ---------------------------------------------------------------------------
# Refresh Tokens (JWT Refresh + Revocation)
# ---------------------------------------------------------------------------

class RefreshToken(UUIDPrimaryKeyMixin, Base):
    """
    Tracks issued refresh tokens to support revocation.
    When a refresh token is used, it's rotated (old one revoked, new one issued).
    """
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        doc="SHA-256 hash of the refresh token",
    )
    jti: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        doc="JWT ID claim from the token - used for revocation",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revocation_reason: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="logout, rotation, security_concern, admin_revoke",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Relationships ---
    user: Mapped[User] = relationship(
        "User",
        back_populates="refresh_tokens",
    )

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        from datetime import timezone
        return datetime.now(timezone.utc) > self.expires_at
