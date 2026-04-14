# Redirect to authoritative models in app/models/
# This file exists for backwards compatibility with legacy imports.
from app.models.user import User
from app.models.audit import AuditTrail as AuditLog
from app.models.agent import AgentProfile, ClientAgentAssignment
from app.core.database import Base

__all__ = [
    "Base",
    "User", "AuditLog",
    "AgentProfile", "ClientAgentAssignment",
]
