"""
The Life Shield - Agent Schemas
Pydantic request/response models for agent profile endpoints.
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# AGENT CREATE / UPDATE
# ─────────────────────────────────────────────

class AgentCreateRequest(BaseModel):
    """Admin creates a new AI agent profile."""
    agent_name: str = Field(..., min_length=1, max_length=100, examples=["tim_shaw"])
    display_name: str = Field(..., min_length=1, max_length=100, examples=["Tim Shaw"])
    role: str = Field("client_success_agent", examples=["client_success_agent", "credit_analyst"])

    # Personality
    tone: Optional[str] = Field(None, max_length=100, examples=["calm, professional, confident"])
    communication_style: Optional[str] = Field(None, max_length=255)
    greeting_template: Optional[str] = None
    closing_template: Optional[str] = None

    # Voice
    voice_provider: Optional[str] = Field(None, examples=["elevenlabs", "google_tts"])
    voice_id: Optional[str] = Field(None, max_length=100)
    speech_rate: float = Field(1.0, ge=0.5, le=2.0)
    pitch: float = Field(1.0, ge=0.5, le=2.0)

    # Avatar
    avatar_type: Optional[str] = Field(None, examples=["tavus", "custom"])
    avatar_id: Optional[str] = Field(None, max_length=100)
    disclosure_text: str = Field(
        "AI Client Agent for The Life Shield",
        max_length=255
    )

    # Specialties (free-form JSON list)
    specialties: Optional[list[str]] = None

    # Knowledge base
    knows_fcra: bool = True
    knows_croa: bool = True
    knows_fcc_rules: bool = True
    knows_nc_regulations: bool = True

    # Permissions
    can_answer_faq: bool = True
    can_explain_status: bool = True
    can_schedule_meetings: bool = True
    can_send_reminders: bool = True
    can_gather_documents: bool = True
    can_recommend_products: bool = False
    can_file_disputes: bool = False
    can_make_promises: bool = False      # Always False per compliance rules
    can_escalate: bool = True
    can_override_decisions: bool = False  # Humans only

    # Capacity
    max_clients: int = Field(2000, ge=1, le=10000)

    model_config = {"json_schema_extra": {"example": {
        "agent_name": "tim_shaw",
        "display_name": "Tim Shaw",
        "role": "client_success_agent",
        "tone": "calm, professional, confident",
        "communication_style": "clear, actionable, empathetic",
        "greeting_template": "Hi, I'm Tim Shaw, your client success agent.",
        "disclosure_text": "AI Client Agent for The Life Shield",
        "voice_provider": "elevenlabs",
        "voice_id": "tim_shaw_voice_001",
        "max_clients": 2000,
    }}}


class AgentUpdateRequest(BaseModel):
    """Admin updates an existing agent profile. All fields optional."""
    display_name: Optional[str] = Field(None, max_length=100)
    role: Optional[str] = None
    tone: Optional[str] = Field(None, max_length=100)
    communication_style: Optional[str] = Field(None, max_length=255)
    greeting_template: Optional[str] = None
    closing_template: Optional[str] = None
    voice_provider: Optional[str] = None
    voice_id: Optional[str] = None
    speech_rate: Optional[float] = Field(None, ge=0.5, le=2.0)
    pitch: Optional[float] = Field(None, ge=0.5, le=2.0)
    avatar_type: Optional[str] = None
    avatar_id: Optional[str] = None
    disclosure_text: Optional[str] = Field(None, max_length=255)
    specialties: Optional[list[str]] = None
    knows_fcra: Optional[bool] = None
    knows_croa: Optional[bool] = None
    knows_fcc_rules: Optional[bool] = None
    knows_nc_regulations: Optional[bool] = None
    can_answer_faq: Optional[bool] = None
    can_explain_status: Optional[bool] = None
    can_schedule_meetings: Optional[bool] = None
    can_send_reminders: Optional[bool] = None
    can_gather_documents: Optional[bool] = None
    can_recommend_products: Optional[bool] = None
    can_file_disputes: Optional[bool] = None
    can_escalate: Optional[bool] = None
    max_clients: Optional[int] = Field(None, ge=1, le=10000)
    is_active: Optional[bool] = None
    is_accepting_clients: Optional[bool] = None


# ─────────────────────────────────────────────
# AGENT RESPONSE
# ─────────────────────────────────────────────

class AgentResponse(BaseModel):
    """Agent profile returned to API consumers."""
    id: uuid.UUID
    agent_name: str
    display_name: str
    role: str
    tone: Optional[str]
    communication_style: Optional[str]
    greeting_template: Optional[str]
    disclosure_text: str
    voice_provider: Optional[str]
    voice_id: Optional[str]
    speech_rate: float
    pitch: float
    avatar_type: Optional[str]
    avatar_id: Optional[str]
    specialties: Optional[Any]
    knows_fcra: bool
    knows_croa: bool
    knows_fcc_rules: bool
    knows_nc_regulations: bool
    can_answer_faq: bool
    can_explain_status: bool
    can_schedule_meetings: bool
    can_send_reminders: bool
    can_gather_documents: bool
    can_recommend_products: bool
    can_file_disputes: bool
    can_make_promises: bool
    can_escalate: bool
    can_override_decisions: bool
    max_clients: int
    assigned_client_count: int
    performance_rating: float
    satisfaction_score: float
    compliance_violations: int
    is_active: bool
    is_accepting_clients: bool
    created_at: datetime
    updated_at: datetime
    active_since: Optional[datetime]

    model_config = {"from_attributes": True}


class AgentListResponse(BaseModel):
    """Paginated agent list."""
    items: list[AgentResponse]
    total: int
    page: int
    per_page: int
    pages: int


# ─────────────────────────────────────────────
# ASSIGN AGENT TO CLIENT
# ─────────────────────────────────────────────

class AgentAssignRequest(BaseModel):
    """Admin assigns an agent to a client user."""
    client_user_id: uuid.UUID
    agent_id: uuid.UUID
    notes: Optional[str] = Field(None, max_length=500)
