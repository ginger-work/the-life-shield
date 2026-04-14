"""
Billing & Product Models

Tables:
- subscriptions     (active plans, billing cycles)
- products          (guides, courses, tools)
- purchases         (transaction history)
- payments          (payment records)
- refunds           (cancellations, chargebacks)
- pricing_rules     (admin-controlled pricing engine)
- affiliate_links   (partner commissions)
- recommendations   (personalized product suggestions)
"""
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index,
    Integer, Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.client import ClientProfile
    from app.models.agent import AgentProfile


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SubscriptionStatus(str, PyEnum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TRIALING = "trialing"


class ProductCategory(str, PyEnum):
    GUIDE = "guide"
    COURSE = "course"
    DIGITAL_TOOL = "digital_tool"
    COACHING_GROUP = "coaching_group"
    COACHING_ONE_ON_ONE = "coaching_one_on_one"
    AFFILIATE = "affiliate"


class PurchaseStatus(str, PyEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    DISPUTED = "disputed"
    FAILED = "failed"


class PaymentStatus(str, PyEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    DISPUTED = "disputed"


class PaymentProcessor(str, PyEnum):
    STRIPE = "stripe"
    PAYPAL = "paypal"
    MANUAL = "manual"   # Admin-entered payment


class PricingRuleType(str, PyEnum):
    BASE_PRICE = "base_price"
    DISCOUNT_PERCENT = "discount_percent"
    DISCOUNT_FIXED = "discount_fixed"
    COUPON = "coupon"
    AFFILIATE = "affiliate"
    PROMO = "promo"


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

class Subscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Client subscription plan tracking.
    One active subscription per client at a time.
    """
    __tablename__ = "subscriptions"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="basic, premium, vip",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="active",
        index=True,
    )

    # Pricing
    price_per_month: Mapped[Numeric] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    billing_interval: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="monthly",
        doc="monthly, annual",
    )

    # Dates
    start_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    end_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    next_billing_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    billing_day_of_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    trial_end_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Auto-renewal
    auto_renew: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    cancellation_at_period_end: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # Stripe Integration
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        unique=True,
        index=True,
    )
    stripe_price_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    # Cancellation
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cancellation_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # --- Relationships ---
    client: Mapped["ClientProfile"] = relationship(
        "ClientProfile",
        back_populates="subscriptions",
    )

    __table_args__ = (
        Index("ix_subscriptions_client_status", "client_id", "status"),
        Index("ix_subscriptions_billing_date", "next_billing_date"),
    )


# ---------------------------------------------------------------------------
# Products (Guides, Courses, Tools)
# ---------------------------------------------------------------------------

class Product(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Admin-managed product catalog.
    AI recommendation engine ONLY recommends from this table at admin-set prices.
    """
    __tablename__ = "products"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    price: Mapped[Numeric] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=0,
        doc="Base price. 0 = free.",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )
    is_free: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # Content
    content_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        doc="S3 URL for digital download (guide, course video)",
    )
    external_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        doc="External URL (affiliate product)",
    )
    thumbnail_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    # Metadata
    tags: Mapped[Optional[List]] = mapped_column(
        JSON,
        nullable=True,
        doc="['credit_repair', 'budgeting', 'beginner']",
    )
    target_audience_criteria: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Conditions for recommendation: {'min_score': 500, 'max_score': 650}",
    )
    duration_minutes: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="For courses and sessions",
    )
    is_affiliate: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    affiliate_disclosure: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Required CROA disclosure for affiliate products",
    )

    # Stats
    total_purchases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_rating: Mapped[Optional[float]] = mapped_column(Numeric(3, 2), nullable=True)

    # Versioning
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    updated_version_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # --- Relationships ---
    recommendations: Mapped[List["Recommendation"]] = relationship(
        "Recommendation",
        back_populates="product",
    )
    purchases: Mapped[List["Purchase"]] = relationship(
        "Purchase",
        back_populates="product",
    )
    affiliate_link: Mapped[Optional["AffiliateLink"]] = relationship(
        "AffiliateLink",
        back_populates="product",
        uselist=False,
    )
    pricing_rules: Mapped[List["PricingRule"]] = relationship(
        "PricingRule",
        primaryjoin="and_(PricingRule.entity_type == 'product', "
                    "PricingRule.entity_id == Product.id)",
        foreign_keys="PricingRule.entity_id",
        overlaps="pricing_rules",
    )


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

class Recommendation(UUIDPrimaryKeyMixin, Base):
    """
    Agent recommendations to clients.
    Recommendations can ONLY reference products in the products table
    at admin-approved prices. AI cannot invent prices or products.
    """
    __tablename__ = "recommendations"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    recommendation_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    reasoning: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Why agent recommended this product",
    )
    compliance_approved: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    price_at_recommendation: Mapped[Optional[Numeric]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        doc="Price shown to client at time of recommendation",
    )
    client_responded: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
    )
    client_response_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # --- Relationships ---
    product: Mapped[Product] = relationship(
        "Product",
        back_populates="recommendations",
    )


# ---------------------------------------------------------------------------
# Purchases
# ---------------------------------------------------------------------------

class Purchase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Transaction record for one-time product purchases."""
    __tablename__ = "purchases"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    price_paid: Mapped[Numeric] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
    )
    purchased_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    refunded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    refund_amount: Mapped[Optional[Numeric]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    stripe_payment_intent_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        unique=True,
    )

    # --- Relationships ---
    client: Mapped["ClientProfile"] = relationship(
        "ClientProfile",
        back_populates="purchases",
    )
    product: Mapped[Product] = relationship(
        "Product",
        back_populates="purchases",
    )


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

class Payment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Full payment ledger - every transaction (subscriptions, purchases, refunds).
    Separate from Purchase to support subscriptions (no associated product row).
    """
    __tablename__ = "payments"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Numeric] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
    )
    processor: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="stripe",
    )
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payment_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        doc="subscription, purchase, coaching, refund",
    )

    # Processor References
    stripe_payment_intent_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        unique=True,
        index=True,
    )
    stripe_invoice_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    paypal_order_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    # Dates
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    refunded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    refund_amount: Mapped[Optional[Numeric]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    failure_reason: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # --- Relationships ---
    client: Mapped["ClientProfile"] = relationship(
        "ClientProfile",
        back_populates="payments",
    )


# ---------------------------------------------------------------------------
# Pricing Rules (Admin-Controlled)
# ---------------------------------------------------------------------------

class PricingRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Admin-set pricing rules.
    AI recommendation engine reads from this table - cannot modify it.
    """
    __tablename__ = "pricing_rules"

    entity_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
        doc="subscription, product, session, group_session",
    )
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        doc="FK to the entity being priced (product_id, etc.)",
    )
    rule_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    value: Mapped[Numeric] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        doc="Price (base_price) or percentage (discount_percent)",
    )
    coupon_code: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        unique=True,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )
    start_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    end_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    max_uses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )


# ---------------------------------------------------------------------------
# Affiliate Links
# ---------------------------------------------------------------------------

class AffiliateLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Affiliate partner links and commission tracking.
    Required disclosure: client must see commission disclosure before clicking.
    """
    __tablename__ = "affiliate_links"

    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    partner_name: Mapped[str] = mapped_column(String(255), nullable=False)
    affiliate_url: Mapped[str] = mapped_column(String(500), nullable=False)
    commission_percentage: Mapped[Optional[Numeric]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )
    commission_fixed: Mapped[Optional[Numeric]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    disclosure_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Required CROA/FTC disclosure shown to client",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    total_clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_conversions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # --- Relationships ---
    product: Mapped[Optional[Product]] = relationship(
        "Product",
        back_populates="affiliate_link",
    )
