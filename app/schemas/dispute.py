"""
Dispute Schemas

Pydantic models for dispute case API requests and responses.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────────────────
# Request Schemas
# ─────────────────────────────────────────────────────────

class CreateDisputeRequest(BaseModel):
    """Create a new dispute case."""
    bureau: str = Field(
        ...,
        description="Bureau to dispute with: 'equifax', 'experian', or 'transunion'",
        examples=["equifax"],
    )
    dispute_reason: str = Field(
        ...,
        description=(
            "Reason for dispute. One of: inaccurate, incomplete, unverifiable, "
            "obsolete, fraudulent, not_mine, wrong_balance, wrong_status, duplicate"
        ),
        examples=["inaccurate"],
    )
    creditor_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the creditor being disputed",
        examples=["Midland Credit Management"],
    )
    account_number_masked: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Last 4 digits or masked account number",
        examples=["****1234"],
    )
    item_description: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Human-readable description of what is being disputed",
    )
    tradeline_id: Optional[uuid.UUID] = Field(
        default=None,
        description="ID of an existing Tradeline record to link this dispute to",
    )
    priority_score: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Priority 1-10 (10 = highest impact)",
    )
    analyst_notes: Optional[str] = Field(
        default=None,
        max_length=5000,
        description="Credit analyst notes",
    )

    @field_validator("bureau")
    @classmethod
    def validate_bureau(cls, v: str) -> str:
        valid = {"equifax", "experian", "transunion"}
        if v.lower() not in valid:
            raise ValueError(f"Invalid bureau: {v}. Must be one of: {valid}")
        return v.lower()

    @field_validator("dispute_reason")
    @classmethod
    def validate_dispute_reason(cls, v: str) -> str:
        valid = {
            "inaccurate", "incomplete", "unverifiable", "obsolete",
            "fraudulent", "not_mine", "wrong_balance", "wrong_status", "duplicate",
        }
        if v.lower() not in valid:
            raise ValueError(f"Invalid dispute_reason: {v}. Must be one of: {valid}")
        return v.lower()


class GenerateLetterRequest(BaseModel):
    """Generate an AI dispute letter for a dispute case."""
    dispute_id: uuid.UUID = Field(
        ...,
        description="ID of the dispute case to generate a letter for",
    )


class ApproveLetterRequest(BaseModel):
    """Admin approves a dispute letter for filing."""
    letter_id: uuid.UUID = Field(
        ...,
        description="ID of the DisputeLetter to approve",
    )


class RejectLetterRequest(BaseModel):
    """Admin rejects a dispute letter with a reason."""
    letter_id: uuid.UUID = Field(
        ...,
        description="ID of the DisputeLetter to reject",
    )
    reason: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Reason for rejection (required)",
    )


class FileDisputeRequest(BaseModel):
    """File an approved dispute with the bureau."""
    dispute_id: uuid.UUID = Field(
        ...,
        description="ID of the approved dispute case to file",
    )
    letter_id: uuid.UUID = Field(
        ...,
        description="ID of the approved dispute letter to submit",
    )


class RecordBureauResponseRequest(BaseModel):
    """Record the bureau's investigation response."""
    response_type: str = Field(
        ...,
        description=(
            "Bureau's outcome. One of: removed, updated, verified, "
            "reinvestigation, deleted, no_response"
        ),
        examples=["removed"],
    )
    response_content: Optional[str] = Field(
        default=None,
        description="Full text of the bureau's response letter",
    )
    score_impact: Optional[int] = Field(
        default=None,
        ge=-200,
        le=200,
        description="Estimated score point change from this outcome",
    )

    @field_validator("response_type")
    @classmethod
    def validate_response_type(cls, v: str) -> str:
        valid = {"removed", "updated", "verified", "reinvestigation", "deleted", "no_response"}
        if v.lower() not in valid:
            raise ValueError(f"Invalid response_type: {v}. Must be one of: {valid}")
        return v.lower()


class WebhookBureauResponse(BaseModel):
    """Inbound webhook payload from a credit bureau."""
    bureau: str
    event_type: str = Field(
        ...,
        description="Bureau event type (dispute_update, report_ready, etc.)",
    )
    confirmation_number: Optional[str] = None
    dispute_status: Optional[str] = None
    outcome: Optional[str] = None
    timestamp: Optional[str] = None
    raw_payload: Optional[Dict[str, Any]] = None


# ─────────────────────────────────────────────────────────
# Response Schemas
# ─────────────────────────────────────────────────────────

class DisputeLetterResponse(BaseModel):
    """Dispute letter details."""
    id: uuid.UUID
    dispute_id: uuid.UUID
    letter_content: str
    letter_version: int
    compliance_status: str
    compliance_flags: Optional[List[str]] = None
    human_approval_required: bool
    approved_by_admin_id: Optional[uuid.UUID] = None
    approval_date: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    status: str
    ai_model_used: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class BureauResponseRecord(BaseModel):
    """Bureau response record."""
    id: uuid.UUID
    dispute_id: uuid.UUID
    received_date: datetime
    response_type: str
    response_content: Optional[str] = None
    score_impact: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DisputeCaseResponse(BaseModel):
    """Full dispute case details."""
    id: uuid.UUID
    client_id: uuid.UUID
    bureau: str
    dispute_reason: str
    creditor_name: Optional[str] = None
    account_number_masked: Optional[str] = None
    item_description: Optional[str] = None
    status: str
    filed_date: Optional[datetime] = None
    expected_response_date: Optional[datetime] = None
    response_received_date: Optional[datetime] = None
    outcome: Optional[str] = None
    outcome_date: Optional[datetime] = None
    score_impact_points: Optional[int] = None
    priority_score: int
    analyst_notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    letters: List[DisputeLetterResponse] = []
    bureau_responses: List[BureauResponseRecord] = []

    model_config = {"from_attributes": True}


class DisputeListResponse(BaseModel):
    """Paginated list of disputes."""
    total: int
    offset: int
    limit: int
    disputes: List[DisputeCaseResponse]


class DisputeStatusResponse(BaseModel):
    """Real-time dispute status from bureau."""
    dispute_id: uuid.UUID
    bureau: str
    confirmation_number: str
    status: str
    outcome: Optional[str] = None
    outcome_description: Optional[str] = None
    checked_at: datetime
    success: bool
    error_message: Optional[str] = None


class DisputeFiledResponse(BaseModel):
    """Response after successfully filing a dispute."""
    success: bool
    dispute_id: uuid.UUID
    bureau: str
    status: str
    filed_date: Optional[datetime] = None
    expected_response_date: Optional[datetime] = None
    message: str


class DisputeCreateResponse(BaseModel):
    """Response after creating a dispute case."""
    success: bool
    dispute_id: uuid.UUID
    status: str
    message: str


class OverdueDisputeResponse(BaseModel):
    """A dispute that is past its 30-day response deadline."""
    id: uuid.UUID
    client_id: uuid.UUID
    bureau: str
    creditor_name: Optional[str] = None
    filed_date: Optional[datetime] = None
    expected_response_date: Optional[datetime] = None
    days_overdue: int
    status: str

    model_config = {"from_attributes": True}
