"""
Credit Report Schemas

Pydantic models for credit report API requests and responses.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────────────────
# Request Schemas
# ─────────────────────────────────────────────────────────

class PullCreditReportRequest(BaseModel):
    """Request to pull credit reports from one or more bureaus."""
    bureaus: List[str] = Field(
        default=["equifax", "experian", "transunion"],
        description="Which bureaus to pull from",
        examples=[["equifax", "experian", "transunion"]],
    )
    pull_type: str = Field(
        default="full",
        description="Type of pull: 'full', 'soft', or 'monitoring'",
        examples=["full"],
    )

    @field_validator("bureaus")
    @classmethod
    def validate_bureaus(cls, v: List[str]) -> List[str]:
        valid = {"equifax", "experian", "transunion"}
        for bureau in v:
            if bureau.lower() not in valid:
                raise ValueError(f"Invalid bureau: {bureau}. Must be one of: {valid}")
        return [b.lower() for b in v]

    @field_validator("pull_type")
    @classmethod
    def validate_pull_type(cls, v: str) -> str:
        valid = {"full", "soft", "monitoring"}
        if v.lower() not in valid:
            raise ValueError(f"Invalid pull_type: {v}. Must be one of: {valid}")
        return v.lower()


class SoftPullRequest(BaseModel):
    """Request a tri-merge soft pull via iSoftPull (no score impact)."""
    pass  # No additional params — uses client's stored identity


# ─────────────────────────────────────────────────────────
# Response Schemas
# ─────────────────────────────────────────────────────────

class TradelineResponse(BaseModel):
    """A single tradeline (account) from a credit report."""
    id: uuid.UUID
    bureau: str
    creditor_name: str
    account_type: Optional[str] = None
    account_number_masked: Optional[str] = None
    status: str
    balance: Optional[float] = None
    credit_limit: Optional[float] = None
    original_amount: Optional[float] = None
    utilization: Optional[float] = None
    date_opened: Optional[datetime] = None
    date_reported: Optional[datetime] = None
    is_disputable: bool
    dispute_reason: Optional[str] = None
    analyst_notes: Optional[str] = None

    model_config = {"from_attributes": True}


class InquiryResponse(BaseModel):
    """A credit inquiry from a credit report."""
    id: uuid.UUID
    bureau: str
    inquirer_name: str
    inquiry_date: datetime
    is_hard_inquiry: bool
    is_disputable: bool

    model_config = {"from_attributes": True}


class CreditScoreSummary(BaseModel):
    """Score summary for one bureau."""
    bureau: str
    score: Optional[int] = None
    score_model: Optional[str] = None
    pull_date: datetime
    negative_items_count: int = 0
    inquiries_count: int = 0
    tradelines_count: int = 0
    collections_count: int = 0


class CreditReportResponse(BaseModel):
    """Full credit report response."""
    id: uuid.UUID
    client_id: uuid.UUID
    bureau: str
    pull_date: datetime
    pull_type: str
    score: Optional[int] = None
    score_model: Optional[str] = None
    report_reference_number: Optional[str] = None
    negative_items_count: int = 0
    inquiries_count: int = 0
    tradelines_count: int = 0
    collections_count: int = 0
    tradelines: List[TradelineResponse] = []
    inquiries: List[InquiryResponse] = []

    model_config = {"from_attributes": True}


class PullCreditReportResponse(BaseModel):
    """Response after initiating a credit report pull."""
    success: bool
    message: str
    reports_pulled: List[str] = Field(description="Bureaus successfully pulled")
    reports_failed: List[str] = Field(default_factory=list, description="Bureaus that failed")
    report_ids: Dict[str, str] = Field(default_factory=dict, description="Bureau → report_id mapping")


class LatestReportsResponse(BaseModel):
    """Client's most recent reports per bureau."""
    client_id: uuid.UUID
    equifax: Optional[CreditScoreSummary] = None
    experian: Optional[CreditScoreSummary] = None
    transunion: Optional[CreditScoreSummary] = None
    scores_updated_at: Optional[datetime] = None
    reports: List[CreditReportResponse] = []


class ScoreHistoryEntry(BaseModel):
    """Single historical score entry."""
    snapshot_date: datetime
    score_equifax: Optional[int] = None
    score_experian: Optional[int] = None
    score_transunion: Optional[int] = None
    negative_items_count: int = 0
    inquiries_count: int = 0


class ScoreHistoryResponse(BaseModel):
    """Score history trend data."""
    client_id: uuid.UUID
    history: List[ScoreHistoryEntry] = []
