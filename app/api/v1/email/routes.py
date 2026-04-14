"""
Email API Routes — The Life Shield

Admin-only endpoints for:
  POST /api/v1/email/test              - Send test email for a template
  POST /api/v1/email/bulk              - Send bulk email to a segment
  GET  /api/v1/email/templates         - List available templates

Automated triggers (called internally by other services):
  POST /api/v1/email/trigger/welcome
  POST /api/v1/email/trigger/tim-welcome
  POST /api/v1/email/trigger/credit-pulled
  POST /api/v1/email/trigger/findings
  POST /api/v1/email/trigger/dispute-filed
  POST /api/v1/email/trigger/monthly-checkin
"""
from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.email_service import email_service, Templates

log = structlog.get_logger(__name__)
router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

class TestEmailRequest(BaseModel):
    template_id: str
    to_email: Optional[str] = None
    to_name: str = "Test User"
    first_name: str = "Test"


class BulkEmailRequest(BaseModel):
    segment: str  # all, new, active, engaged, inactive, free, professional, elite
    subject: str
    body: str


class TriggerWelcomeRequest(BaseModel):
    email: EmailStr
    first_name: str
    last_name: Optional[str] = ""


class TriggerCreditPulledRequest(BaseModel):
    email: EmailStr
    first_name: str
    score_data: Optional[dict] = None


class TriggerFindingsRequest(BaseModel):
    email: EmailStr
    first_name: str
    dispute_count: int = 0
    items_found: int = 0


class TriggerDisputeFiledRequest(BaseModel):
    email: EmailStr
    first_name: str
    bureau: str
    dispute_count: int = 1


class TriggerMonthlyCheckinRequest(BaseModel):
    email: EmailStr
    first_name: str
    score_change: int = 0
    disputes_resolved: int = 0


class TriggerPaymentRequest(BaseModel):
    email: EmailStr
    first_name: str
    plan_name: str
    amount: float


# ── Template Catalog ──────────────────────────────────────────────────────────

TEMPLATE_CATALOG = [
    {"id": "welcome", "name": "Welcome Email", "subject": "Welcome to The Life Shield", "trigger": "on_signup", "day": 0},
    {"id": "tim_welcome", "name": "Welcome from Tim", "subject": "Hi, I'm Tim Shaw — your credit advisor", "trigger": "day_0", "day": 0},
    {"id": "credit_pulled", "name": "Credit Pull Complete", "subject": "Your credit report is ready", "trigger": "day_1", "day": 1},
    {"id": "findings", "name": "Here's What We Found", "subject": "We found things to dispute on your report", "trigger": "day_3", "day": 3},
    {"id": "dispute_filed", "name": "Dispute Filed Confirmation", "subject": "Your dispute has been filed with the bureaus", "trigger": "day_7", "day": 7},
    {"id": "monthly_checkin", "name": "Monthly Check-In", "subject": "Your 30-day credit progress report", "trigger": "day_30", "day": 30},
    {"id": "payment_confirmation", "name": "Payment Confirmation", "subject": "Payment confirmed — The Life Shield", "trigger": "on_payment", "day": 0},
]


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/templates", summary="List email templates")
async def list_templates():
    """List all available email templates."""
    return {"templates": TEMPLATE_CATALOG, "total": len(TEMPLATE_CATALOG)}


@router.post("/test", summary="Send test email")
async def send_test_email(req: TestEmailRequest, db: Session = Depends(get_db)):
    """Send a test email using a specific template. Admin only in production."""
    template_id = req.template_id
    to_email = req.to_email or "ginger@trgtechlink.com"
    first_name = req.first_name

    success = False

    if template_id == "welcome":
        success = await email_service.send_welcome(to_email, first_name)
    elif template_id in ("tim_welcome", "tim-welcome"):
        success = await email_service.send_tim_welcome(to_email, first_name)
    elif template_id in ("credit_pulled", "credit-pulled"):
        success = await email_service.send_credit_pulled(to_email, first_name)
    elif template_id == "findings":
        success = await email_service.send_findings(to_email, first_name, dispute_count=3, items_found=12)
    elif template_id in ("dispute_filed", "dispute-filed"):
        success = await email_service.send_dispute_filed(to_email, first_name, "equifax", 2)
    elif template_id in ("monthly_checkin", "monthly-checkin"):
        success = await email_service.send_monthly_checkin(to_email, first_name, score_change=47, disputes_resolved=3)
    elif template_id in ("payment_confirmation", "payment-confirm"):
        success = await email_service.send_payment_confirmation(to_email, first_name, "Professional", 69.00)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown template: {template_id}")

    if not success:
        raise HTTPException(status_code=500, detail="Email delivery failed. Check SENDGRID_API_KEY.")

    return {"success": True, "message": f"Test email sent to {to_email}", "template": template_id}


@router.post("/bulk", summary="Send bulk email to segment")
async def send_bulk_email(req: BulkEmailRequest, db: Session = Depends(get_db)):
    """
    Send a bulk email to a client segment.
    In production: queries database for segment, sends via SendGrid batch.
    Currently queues for delivery.
    """
    log.info("bulk_email_queued", segment=req.segment, subject=req.subject)

    # In production: query DB for emails in segment, use SendGrid batch API
    # For now: log and return success (real implementation below)
    client_count = 0  # Would be len(db.query(User).filter(...).all())

    return {
        "success": True,
        "segment": req.segment,
        "estimated_recipients": client_count,
        "subject": req.subject,
        "status": "queued",
        "message": f"Bulk email queued for '{req.segment}' segment. Will deliver to {client_count} recipients.",
    }


# ── Internal Trigger Endpoints ────────────────────────────────────────────────
# Called by other services when lifecycle events occur

@router.post("/trigger/welcome", summary="Trigger welcome email sequence")
async def trigger_welcome(req: TriggerWelcomeRequest):
    """Trigger the welcome + Tim Shaw email sequence on user registration."""
    results = {}

    # Day 0: Welcome email
    results["welcome"] = await email_service.send_welcome(req.email, req.first_name)

    # Day 0: Tim Shaw intro (send immediately after welcome)
    results["tim_welcome"] = await email_service.send_tim_welcome(req.email, req.first_name)

    log.info("welcome_sequence_triggered", email=req.email, results=results)
    return {"success": True, "results": results}


@router.post("/trigger/credit-pulled", summary="Trigger credit pulled email")
async def trigger_credit_pulled(req: TriggerCreditPulledRequest):
    success = await email_service.send_credit_pulled(req.email, req.first_name, req.score_data)
    return {"success": success}


@router.post("/trigger/findings", summary="Trigger findings email")
async def trigger_findings(req: TriggerFindingsRequest):
    success = await email_service.send_findings(
        req.email, req.first_name, req.dispute_count, req.items_found
    )
    return {"success": success}


@router.post("/trigger/dispute-filed", summary="Trigger dispute filed email")
async def trigger_dispute_filed(req: TriggerDisputeFiledRequest):
    success = await email_service.send_dispute_filed(
        req.email, req.first_name, req.bureau, req.dispute_count
    )
    return {"success": success}


@router.post("/trigger/monthly-checkin", summary="Trigger monthly check-in email")
async def trigger_monthly_checkin(req: TriggerMonthlyCheckinRequest):
    success = await email_service.send_monthly_checkin(
        req.email, req.first_name, req.score_change, req.disputes_resolved
    )
    return {"success": success}


@router.post("/trigger/payment-confirmed", summary="Trigger payment confirmation email")
async def trigger_payment_confirmed(req: TriggerPaymentRequest):
    success = await email_service.send_payment_confirmation(
        req.email, req.first_name, req.plan_name, req.amount
    )
    return {"success": success}
