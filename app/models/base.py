"""
Base model mixin providing common columns for all tables.
Every table inherits: id, created_at, updated_at.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TimestampMixin:
    """
    Provides created_at and updated_at columns.
    updated_at is automatically set on every UPDATE.
    """
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="UTC timestamp when record was created",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        doc="UTC timestamp when record was last modified",
    )


class UUIDPrimaryKeyMixin:
    """
    Provides a UUID primary key column named `id`.
    UUIDs prevent ID enumeration attacks and work across distributed systems.
    """
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="UUID primary key",
    )
