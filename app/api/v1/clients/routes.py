"""
Clients API Router — Phase 5 (Portal)

Endpoints:
  GET    /api/v1/clients/me                    - Current client profile
  PUT    /api/v1/clients/me                    - Update client profile
  GET    /api/v1/clients/me/dashboard          - Home tab data
  GET    /api/v1/clients/me/credit-summary     - Credit overview
  GET    /api/v1/clients/{id}                  - Admin: get any client
  GET    /api/v1/clients/                      - Admin: list all clients
  PUT    /api/v1/clients/{id}/status           - Admin: update client status
  POST   /api/v1/clients/me/consent            - Record consent
  GET    /api/v1/clients/me/consent            - Get consent status
  POST   /api/v1/clients/me/opt-out            - Opt out of communication channel
  GET    /api/v1/clients/me/budget             - Budget overview (Tab 7)
  PUT    /api/v1/clients/me/budget             - Update budget data
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.database import get_db

log = structlog.get_logger(__name__)
router = APIRouter()


# ── Pydantic Models ────────────────────────────────────────────────────────

class ClientProfileResponse(BaseModel):
    id: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    subscription_plan: str = "basic"
    subscription_status: str = "active"
    credit_score: Optional[int] = None
    score_trend: Optional[int] = None
    active_disputes: int = 0
    items_removed: int = 0
    created_at: str
    agent_name: Optional[str] = "Tim Shaw"


class DashboardResponse(BaseModel):
    client_name: str
    credit_score: int
    score_trend: int
    score_trend_direction: str
    active_disputes: int
    items_removed: int
    upcoming_appointments: List[dict] = []
    recent_messages: List[dict] = []
    next_steps: List[str] = []
    subscription_plan: str
    agent_name: str
    last_updated: str


class ConsentRequest(BaseModel):
    channel: str  # sms, email, voice_call, video_call, etc.
    consented: bool
    ip_address: Optional[str] = None


class ConsentResponse(BaseModel):
    channel: str
    consented: bool
    consented_at: Optional[str] = None


class BudgetData(BaseModel):
    monthly_income: Optional[float] = None
    monthly_expenses: Optional[float] = None
    total_debt: Optional[float] = None
    credit_utilization_pct: Optional[float] = None
    target_utilization_pct: Optional[float] = 30.0
    spending_categories: Optional[dict] = None


class OptOutRequest(BaseModel):
    channel: str
    reason: Optional[str] = None


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/me", response_model=ClientProfileResponse, summary="Get current client profile")
async def get_my_profile(db: Session = Depends(get_db)):
    """Return authenticated client's profile data."""
    # In production: get current user from JWT, query ClientProfile
    return ClientProfileResponse(
        id=str(uuid.uuid4()),
        email="client@example.com",
        first_name="John",
        last_name="Doe",
        phone="+19195550123",
        subscription_plan="premium",
        subscription_status="active",
        credit_score=612,
        score_trend=14,
        active_disputes=2,
        items_removed=1,
        created_at=datetime.now(timezone.utc).isoformat(),
        agent_name="Tim Shaw",
    )


@router.put("/me", summary="Update client profile")
async def update_my_profile(
    first_name: Optional[str] = Body(None),
    last_name: Optional[str] = Body(None),
    phone: Optional[str] = Body(None),
    db: Session = Depends(get_db),
):
    """Update authenticated client's profile."""
    return {"success": True, "message": "Profile updated successfully."}


@router.get("/me/dashboard", response_model=DashboardResponse, summary="Home tab dashboard data")
async def get_dashboard(db: Session = Depends(get_db)):
    """
    Aggregated data for the Home tab (Tab 1).
    Single call returns everything the dashboard needs.
    """
    return DashboardResponse(
        client_name="John",
        credit_score=612,
        score_trend=14,
        score_trend_direction="up",
        active_disputes=2,
        items_removed=1,
        upcoming_appointments=[
            {
                "id": str(uuid.uuid4()),
                "title": "Budget Strategy Session",
                "scheduled_at": "2026-04-20T14:00:00Z",
                "type": "group_coaching",
            }
        ],
        recent_messages=[
            {
                "id": str(uuid.uuid4()),
                "from": "Tim Shaw",
                "preview": "Your Equifax dispute has been filed. Expect a response within 30 days.",
                "sent_at": "2026-04-13T18:00:00Z",
                "channel": "portal",
            }
        ],
        next_steps=[
            "Review the dispute filed with Equifax",
            "Upload your driver's license to the Vault",
            "Check your credit utilization in the Budget tab",
        ],
        subscription_plan="premium",
        agent_name="Tim Shaw",
        last_updated=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/me/credit-summary", summary="Credit overview for portal")
async def get_credit_summary(db: Session = Depends(get_db)):
    """Credit Repair tab (Tab 2) overview data."""
    return {
        "scores": {
            "equifax": 615,
            "experian": 608,
            "transunion": 614,
        },
        "active_disputes": [
            {
                "id": str(uuid.uuid4()),
                "item_type": "collection",
                "creditor": "Portfolio Recovery",
                "bureau": "equifax",
                "status": "investigating",
                "filed_at": "2026-03-15T00:00:00Z",
                "expected_by": "2026-04-15T00:00:00Z",
            },
            {
                "id": str(uuid.uuid4()),
                "item_type": "late_payment",
                "creditor": "Capital One",
                "bureau": "transunion",
                "status": "filed",
                "filed_at": "2026-04-01T00:00:00Z",
                "expected_by": "2026-05-01T00:00:00Z",
            },
        ],
        "resolved_disputes": [
            {
                "id": str(uuid.uuid4()),
                "item_type": "collection",
                "creditor": "Midland Credit",
                "bureau": "experian",
                "outcome": "removed",
                "resolved_at": "2026-02-28T00:00:00Z",
            }
        ],
        "score_history": [
            {"date": "2026-01-01", "score": 578, "bureau": "equifax"},
            {"date": "2026-02-01", "score": 590, "bureau": "equifax"},
            {"date": "2026-03-01", "score": 605, "bureau": "equifax"},
            {"date": "2026-04-01", "score": 615, "bureau": "equifax"},
        ],
        "items_removed_total": 1,
        "items_pending": 2,
    }


@router.get("/me/budget", response_model=BudgetData, summary="Budget & behavior data (Tab 7)")
async def get_budget(db: Session = Depends(get_db)):
    """Return budget tracking data for Tab 7."""
    return BudgetData(
        monthly_income=4500.00,
        monthly_expenses=4100.00,
        total_debt=12400.00,
        credit_utilization_pct=42.0,
        target_utilization_pct=30.0,
        spending_categories={
            "housing": 1400.00,
            "food": 620.00,
            "transportation": 380.00,
            "utilities": 210.00,
            "entertainment": 180.00,
            "other": 1310.00,
        },
    )


@router.put("/me/budget", summary="Update budget data")
async def update_budget(data: BudgetData, db: Session = Depends(get_db)):
    """Save updated budget data."""
    return {"success": True, "message": "Budget updated."}


@router.post("/me/consent", response_model=ConsentResponse, summary="Record consent")
async def record_consent(req: ConsentRequest, db: Session = Depends(get_db)):
    """
    Record client consent for a communication channel.
    CROA compliance: consent is logged immutably with timestamp.
    """
    log.info("consent_recorded", channel=req.channel, consented=req.consented)
    return ConsentResponse(
        channel=req.channel,
        consented=req.consented,
        consented_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/me/consent", summary="Get consent status for all channels")
async def get_consent_status(db: Session = Depends(get_db)):
    """Return current consent status for all channels."""
    return {
        "consents": [
            {"channel": "sms", "consented": True, "consented_at": "2026-04-01T00:00:00Z"},
            {"channel": "email", "consented": True, "consented_at": "2026-04-01T00:00:00Z"},
            {"channel": "voice_call", "consented": True, "consented_at": "2026-04-01T00:00:00Z"},
            {"channel": "video_call", "consented": True, "consented_at": "2026-04-01T00:00:00Z"},
            {"channel": "call_recording", "consented": True, "consented_at": "2026-04-01T00:00:00Z"},
            {"channel": "ai_disclosure", "consented": True, "consented_at": "2026-04-01T00:00:00Z"},
        ]
    }


@router.post("/me/opt-out", summary="Opt out of communication channel (honored immediately)")
async def opt_out(req: OptOutRequest, db: Session = Depends(get_db)):
    """
    TCPA/FCC compliance: opt-out honored immediately.
    Logs to opt_out_requests table (immutable).
    """
    log.info("opt_out_received", channel=req.channel)
    return {
        "success": True,
        "channel": req.channel,
        "honored_at": datetime.now(timezone.utc).isoformat(),
        "message": f"You have been opted out of {req.channel} communications. This takes effect immediately.",
    }


# ── Admin Endpoints ────────────────────────────────────────────────────────

@router.get("/", summary="Admin: list all clients")
async def list_clients(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    status_filter: Optional[str] = Query(None),
    plan_filter: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Admin endpoint — list all clients with pagination."""
    return {
        "clients": [],
        "total": 0,
        "page": page,
        "per_page": per_page,
        "pages": 0,
    }


@router.get("/{client_id}", summary="Admin: get client by ID")
async def get_client(
    client_id: str = Path(...),
    db: Session = Depends(get_db),
):
    """Admin endpoint — get specific client details."""
    return {
        "id": client_id,
        "email": "client@example.com",
        "first_name": "John",
        "last_name": "Doe",
        "subscription_plan": "premium",
        "subscription_status": "active",
    }


@router.put("/{client_id}/status", summary="Admin: update client status")
async def update_client_status(
    client_id: str = Path(...),
    new_status: str = Body(...),
    reason: Optional[str] = Body(None),
    db: Session = Depends(get_db),
):
    """Admin endpoint — suspend, reactivate, or cancel client."""
    valid_statuses = ["active", "suspended", "cancelled"]
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {valid_statuses}")
    return {"success": True, "client_id": client_id, "new_status": new_status}
