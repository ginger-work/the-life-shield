"""
Document Model

Stores references to client documents (uploaded or generated).
All actual file content lives in S3; this table is the index.

Tables:
- documents    (document metadata and S3 references)
"""
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.client import ClientProfile


class DocumentType(str, PyEnum):
    CREDIT_REPORT = "credit_report"
    DISPUTE_LETTER = "dispute_letter"
    BUREAU_RESPONSE = "bureau_response"
    ID_VERIFICATION = "id_verification"
    PROOF_OF_FILING = "proof_of_filing"
    CONTRACT = "contract"
    CONSENT_FORM = "consent_form"
    OTHER = "other"


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Document metadata and S3 reference.
    Never stores file content directly — only S3 URL + metadata.
    """
    __tablename__ = "documents"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploaded_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        doc="Admin or system user who created/uploaded this document",
    )

    document_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Storage
    s3_key: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        doc="S3 object key (path within bucket)",
    )
    s3_bucket: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    s3_url: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        doc="Full S3 URL (or presigned URL at generation time)",
    )
    file_size_bytes: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    mime_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="application/pdf, image/jpeg, etc.",
    )
    file_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        doc="SHA-256 hash for integrity verification",
    )

    # Access control
    is_encrypted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        doc="Whether the S3 object is encrypted at rest",
    )
    is_confidential: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        doc="Confidential documents require extra access controls",
    )

    # Retention
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="If set, document auto-expires (for temp presigned URLs)",
    )

    # --- Relationships ---
    client: Mapped["ClientProfile"] = relationship(
        "ClientProfile",
        back_populates="documents",
    )

    __table_args__ = (
        Index("ix_documents_client_type", "client_id", "document_type"),
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} type={self.document_type} title={self.title!r}>"
