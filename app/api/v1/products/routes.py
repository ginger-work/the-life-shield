"""
Products API Router — Phase 5 (Store Tab) + Phase 6 (Admin)

Endpoints:
  GET    /api/v1/products/                        - List all products (client: filtered)
  GET    /api/v1/products/{id}                    - Get product details
  POST   /api/v1/products/{id}/purchase           - Purchase a product (Stripe)
  GET    /api/v1/products/recommendations         - AI recommendations for current client
  GET    /api/v1/products/subscriptions/plans     - Available subscription plans
  GET    /api/v1/products/subscriptions/me        - Current subscription
  POST   /api/v1/products/subscriptions/upgrade   - Upgrade/downgrade plan
  POST   /api/v1/products/subscriptions/cancel    - Cancel subscription (3-day refund)
  GET    /api/v1/products/purchases/me            - Client's purchase history

  # Admin
  POST   /api/v1/products/admin/                  - Create product
  PUT    /api/v1/products/admin/{id}              - Update product + pricing
  DELETE /api/v1/products/admin/{id}              - Archive product
  GET    /api/v1/products/admin/pricing           - View all pricing rules
  POST   /api/v1/products/admin/pricing           - Create pricing rule
  GET    /api/v1/products/admin/revenue           - Revenue summary

PRICING RULES:
  - Admin ONLY can set prices
  - AI recommendation engine pulls prices from admin-approved catalog
  - NO price overrides allowed outside admin controls
  - Affiliate commissions MUST include disclosure
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db

log = structlog.get_logger(__name__)
router = APIRouter()


# ── Pydantic Models ────────────────────────────────────────────────────────

class ProductResponse(BaseModel):
    id: str
    name: str
    category: str
    price: float
    description: str
    is_free: bool
    is_available: bool
    affiliate_disclosure: Optional[str] = None


class SubscriptionPlanResponse(BaseModel):
    plan_id: str
    name: str
    price_monthly: float
    features: List[str]
    dispute_limit: Optional[int] = None
    support_sla_hours: Optional[int] = None


class SubscriptionResponse(BaseModel):
    plan: str
    status: str
    started_at: str
    next_billing_date: Optional[str] = None
    price_monthly: float
    cancellation_policy: str


class PurchaseRequest(BaseModel):
    product_id: str
    payment_method_id: Optional[str] = None  # Stripe payment method


class AdminProductCreate(BaseModel):
    name: str
    category: str
    price: float
    description: str
    is_available: bool = True
    target_score_min: int = 0
    target_score_max: int = 850
    affiliate_commission_pct: Optional[float] = None
    affiliate_disclosure: Optional[str] = None


# ── Product Catalog ────────────────────────────────────────────────────────

PRODUCT_CATALOG = [
    {
        "id": "prod-001",
        "name": "How to Read Your Credit Report",
        "category": "guide",
        "price": 0.00,
        "description": "Free guide to understanding every section of your credit report.",
        "is_free": True,
        "is_available": True,
        "download_url": "/products/guides/how-to-read-credit-report.pdf",
    },
    {
        "id": "prod-002",
        "name": "Understanding FICO Scores",
        "category": "guide",
        "price": 0.00,
        "description": "Learn exactly how FICO calculates your score and what drives it.",
        "is_free": True,
        "is_available": True,
    },
    {
        "id": "prod-003",
        "name": "Dispute Strategy Guide",
        "category": "guide",
        "price": 19.99,
        "description": "Step-by-step guide to writing effective dispute letters.",
        "is_free": False,
        "is_available": True,
    },
    {
        "id": "prod-004",
        "name": "Credit Building Fundamentals",
        "category": "course",
        "price": 49.00,
        "description": "Video course: learn the fundamentals of building and repairing credit.",
        "is_free": False,
        "is_available": True,
    },
    {
        "id": "prod-005",
        "name": "Budget Mastery",
        "category": "course",
        "price": 59.00,
        "description": "Master your budget to reduce utilization and improve your score.",
        "is_free": False,
        "is_available": True,
    },
    {
        "id": "prod-006",
        "name": "Advanced Credit Strategies",
        "category": "course",
        "price": 99.00,
        "description": "Advanced tactics for credit optimization and score maximization.",
        "is_free": False,
        "is_available": True,
    },
    {
        "id": "prod-007",
        "name": "Dispute Strategy Bootcamp (Group)",
        "category": "coaching_group",
        "price": 49.00,
        "description": "90-minute live group coaching session. Workbook included.",
        "is_free": False,
        "is_available": True,
    },
    {
        "id": "prod-008",
        "name": "One-on-One Strategy Session",
        "category": "coaching_one_on_one",
        "price": 200.00,
        "description": "60-minute personal strategy session with a specialist.",
        "is_free": False,
        "is_available": True,
    },
    {
        "id": "prod-009",
        "name": "Homebuying with Bad Credit",
        "category": "guide",
        "price": 9.99,
        "description": "How to prepare for a mortgage while repairing your credit.",
        "is_free": False,
        "is_available": True,
    },
    {
        "id": "prod-010",
        "name": "Budget Planner Template",
        "category": "digital_tool",
        "price": 4.99,
        "description": "Professional budget planner spreadsheet template.",
        "is_free": False,
        "is_available": True,
    },
]

SUBSCRIPTION_PLANS = [
    {
        "plan_id": "basic",
        "name": "Basic Plan",
        "price_monthly": 29.99,
        "features": [
            "Portal access",
            "Unlimited chat with Tim Shaw",
            "Educational content library",
            "Monthly credit report pull",
            "Email support",
            "Up to 5 disputes per month",
            "Cancel anytime (3-day refund guarantee)",
        ],
        "dispute_limit": 5,
        "support_sla_hours": 48,
    },
    {
        "plan_id": "premium",
        "name": "Premium Plan",
        "price_monthly": 79.99,
        "features": [
            "Everything in Basic",
            "Unlimited dispute filing",
            "Priority support (1-hour response)",
            "Exclusive coaching webinars",
            "Unlimited document vault",
            "Budget & behavior coaching",
            "Monthly 1-on-1 strategy call",
        ],
        "dispute_limit": None,  # Unlimited
        "support_sla_hours": 1,
    },
    {
        "plan_id": "vip",
        "name": "VIP Plan",
        "price_monthly": 199.99,
        "features": [
            "Everything in Premium",
            "Weekly 1-on-1 coaching calls",
            "Personal dispute strategy",
            "Priority escalation",
            "Dedicated coordinator",
            "Quarterly financial review",
            "Exclusive products & offers",
        ],
        "dispute_limit": None,
        "support_sla_hours": 0,  # Immediate
    },
]


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/", summary="List products in store")
async def list_products(
    category: Optional[str] = Query(None),
    free_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Return product catalog, optionally filtered."""
    products = PRODUCT_CATALOG.copy()
    if category:
        products = [p for p in products if p["category"] == category]
    if free_only:
        products = [p for p in products if p["is_free"]]
    return {"products": products, "total": len(products)}


@router.get("/recommendations", summary="Personalized AI recommendations")
async def get_recommendations(db: Session = Depends(get_db)):
    """
    Recommendation Engine — personalized product picks.
    Only recommends admin-approved products.
    Affiliate products include mandatory FTC disclosure.
    """
    from agents.specialist_engines import RecommendationEngine
    engine = RecommendationEngine("current-client", db)
    result = engine.recommend_for_client(credit_score=612)

    return {
        "recommendations": result.get("products", []),
        "personalized_message": result.get("response", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/subscriptions/plans", summary="Get all subscription plans")
async def get_subscription_plans():
    """Return all available subscription plans and pricing."""
    return {
        "plans": SUBSCRIPTION_PLANS,
        "note": "All plans include 3-day cancellation with full refund guarantee.",
        "croa_compliance": "No upfront fees. Payment processed after service begins.",
    }


@router.get("/subscriptions/me", response_model=SubscriptionResponse, summary="Get current subscription")
async def get_my_subscription(db: Session = Depends(get_db)):
    """Return current client's active subscription."""
    return SubscriptionResponse(
        plan="premium",
        status="active",
        started_at="2026-04-01T00:00:00Z",
        next_billing_date="2026-05-01T00:00:00Z",
        price_monthly=79.99,
        cancellation_policy="Cancel anytime. 3-day full refund guarantee from billing date.",
    )


@router.post("/subscriptions/upgrade", summary="Upgrade or downgrade subscription plan")
async def change_subscription(
    new_plan: str = Body(..., embed=True),
    db: Session = Depends(get_db),
):
    """Change subscription plan. Prorated billing applies."""
    valid_plans = ["basic", "premium", "vip"]
    if new_plan not in valid_plans:
        raise HTTPException(status_code=400, detail=f"Plan must be one of: {valid_plans}")

    plan = next(p for p in SUBSCRIPTION_PLANS if p["plan_id"] == new_plan)
    return {
        "success": True,
        "new_plan": new_plan,
        "new_price_monthly": plan["price_monthly"],
        "effective_immediately": True,
        "prorated": True,
    }


@router.post("/subscriptions/cancel", summary="Cancel subscription (3-day refund policy)")
async def cancel_subscription(
    reason: Optional[str] = Body(None, embed=True),
    db: Session = Depends(get_db),
):
    """
    Cancel subscription.
    CROA compliance: 3-day full refund guarantee honored automatically.
    """
    return {
        "success": True,
        "cancelled_at": datetime.now(timezone.utc).isoformat(),
        "refund_eligible": True,
        "refund_amount": 79.99,
        "refund_policy": "Full refund within 3 business days. CROA-compliant.",
        "reason_recorded": bool(reason),
        "data_retained": "90 days per our privacy policy",
    }


@router.get("/{product_id}", response_model=ProductResponse, summary="Get product details")
async def get_product(product_id: str = Path(...), db: Session = Depends(get_db)):
    """Get a specific product's details."""
    product = next((p for p in PRODUCT_CATALOG if p["id"] == product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    return ProductResponse(**{k: product.get(k) for k in ProductResponse.model_fields})


@router.post("/{product_id}/purchase", summary="Purchase a product")
async def purchase_product(
    product_id: str = Path(...),
    req: PurchaseRequest = Body(...),
    db: Session = Depends(get_db),
):
    """
    Process product purchase via Stripe.
    In production: create Stripe PaymentIntent and confirm.
    """
    product = next((p for p in PRODUCT_CATALOG if p["id"] == product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    if product["is_free"]:
        # Free product — just grant access
        return {
            "success": True,
            "transaction_id": str(uuid.uuid4()),
            "product": product["name"],
            "amount_charged": 0.00,
            "access_granted": True,
        }

    # In production: process Stripe payment
    return {
        "success": True,
        "transaction_id": str(uuid.uuid4()),
        "product": product["name"],
        "amount_charged": product["price"],
        "payment_status": "completed",
        "access_granted": True,
        "receipt_sent_to": "client@example.com",
    }


@router.get("/purchases/me", summary="Client purchase history")
async def get_my_purchases(
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Return client's purchase history."""
    return {
        "purchases": [
            {
                "id": str(uuid.uuid4()),
                "product_name": "Dispute Strategy Guide",
                "amount": 19.99,
                "status": "completed",
                "purchased_at": "2026-04-05T00:00:00Z",
            }
        ],
        "total": 1,
    }


# ── Admin Endpoints ────────────────────────────────────────────────────────

@router.post("/admin/", status_code=201, summary="Admin: create product")
async def admin_create_product(req: AdminProductCreate, db: Session = Depends(get_db)):
    """Admin: add new product to catalog."""
    product_id = f"prod-{uuid.uuid4().hex[:8]}"
    log.info("product_created", product_id=product_id, name=req.name)
    return {
        "success": True,
        "product_id": product_id,
        "name": req.name,
        "price": req.price,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@router.put("/admin/{product_id}", summary="Admin: update product and pricing")
async def admin_update_product(
    product_id: str = Path(...),
    updates: dict = Body(...),
    db: Session = Depends(get_db),
):
    """Admin: update product details or pricing. Only admin can change prices."""
    log.info("product_updated", product_id=product_id, fields=list(updates.keys()))
    return {"success": True, "product_id": product_id, "updated": updates}


@router.delete("/admin/{product_id}", summary="Admin: archive product")
async def admin_archive_product(product_id: str = Path(...), db: Session = Depends(get_db)):
    """Admin: archive (soft-delete) a product."""
    return {"success": True, "product_id": product_id, "status": "archived"}


@router.get("/admin/pricing", summary="Admin: view all pricing rules")
async def admin_get_pricing(db: Session = Depends(get_db)):
    """Admin: see all active pricing rules."""
    return {
        "pricing_rules": [
            {"plan": "basic", "price": 29.99, "effective_date": "2026-01-01"},
            {"plan": "premium", "price": 79.99, "effective_date": "2026-01-01"},
            {"plan": "vip", "price": 199.99, "effective_date": "2026-01-01"},
        ],
        "last_updated": "2026-04-01T00:00:00Z",
        "updated_by": "admin",
    }


@router.get("/admin/revenue", summary="Admin: revenue summary")
async def admin_revenue_summary(
    period: str = Query("monthly", description="daily, weekly, monthly, yearly"),
    db: Session = Depends(get_db),
):
    """Admin: revenue breakdown by source."""
    return {
        "period": period,
        "subscription_revenue": 0.00,
        "coaching_revenue": 0.00,
        "digital_products_revenue": 0.00,
        "affiliate_revenue": 0.00,
        "total_revenue": 0.00,
        "mrr": 0.00,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
