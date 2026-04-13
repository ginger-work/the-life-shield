#!/usr/bin/env python3
"""
The Life Shield — Database Seed Script
Loads test data for local development.
Usage: python scripts/seed.py
       make seed
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
import uuid

print("🌱 The Life Shield — Seeding test data...")


# ---- Seed Functions ----

def seed_subscription_tiers(db):
    """Create subscription tier records."""
    tiers = [
        {
            "id": str(uuid.uuid4()),
            "name": "Free",
            "slug": "free",
            "price_monthly": 0.00,
            "price_annual": 0.00,
            "features": {
                "credit_monitoring": False,
                "dispute_automation": False,
                "ai_agent_access": "limited",
                "documents_per_month": 2,
            },
            "is_active": True,
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Basic",
            "slug": "basic",
            "price_monthly": 49.00,
            "price_annual": 490.00,
            "features": {
                "credit_monitoring": True,
                "dispute_automation": True,
                "ai_agent_access": "standard",
                "documents_per_month": 10,
            },
            "is_active": True,
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Premium",
            "slug": "premium",
            "price_monthly": 99.00,
            "price_annual": 990.00,
            "features": {
                "credit_monitoring": True,
                "dispute_automation": True,
                "ai_agent_access": "full",
                "documents_per_month": -1,  # unlimited
                "dedicated_agent": True,
                "video_calls": True,
            },
            "is_active": True,
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Enterprise",
            "slug": "enterprise",
            "price_monthly": 299.00,
            "price_annual": 2990.00,
            "features": {
                "credit_monitoring": True,
                "dispute_automation": True,
                "ai_agent_access": "full",
                "documents_per_month": -1,
                "dedicated_agent": True,
                "video_calls": True,
                "priority_support": True,
                "custom_branding": True,
            },
            "is_active": True,
        },
    ]
    print(f"  ✅ Subscription tiers: {len(tiers)} records ready")
    return tiers


def seed_test_clients():
    """Create test client accounts for development."""
    clients = [
        {
            "id": str(uuid.uuid4()),
            "email": "john.doe@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "phone": "+15551234001",
            "date_of_birth": "1985-03-15",
            "ssn_last4": "1234",
            "subscription_tier": "premium",
            "ai_agent_name": "Tim Shaw",
            "consented_to_sms": True,
            "consented_to_email": True,
            "consented_to_calls": True,
            "consented_to_recording": True,
            "consented_to_ai": True,
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "id": str(uuid.uuid4()),
            "email": "jane.smith@example.com",
            "first_name": "Jane",
            "last_name": "Smith",
            "phone": "+15551234002",
            "date_of_birth": "1990-07-22",
            "ssn_last4": "5678",
            "subscription_tier": "basic",
            "ai_agent_name": "Tim Shaw",
            "consented_to_sms": True,
            "consented_to_email": True,
            "consented_to_calls": False,
            "consented_to_recording": False,
            "consented_to_ai": True,
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "id": str(uuid.uuid4()),
            "email": "test.user@example.com",
            "first_name": "Test",
            "last_name": "User",
            "phone": "+15551234003",
            "date_of_birth": "1978-11-08",
            "ssn_last4": "9012",
            "subscription_tier": "free",
            "ai_agent_name": "Tim Shaw",
            "consented_to_sms": True,
            "consented_to_email": True,
            "consented_to_calls": True,
            "consented_to_recording": True,
            "consented_to_ai": True,
            "created_at": datetime.utcnow().isoformat(),
        },
    ]
    print(f"  ✅ Test clients: {len(clients)} accounts ready")
    return clients


def seed_sample_disputes():
    """Sample dispute records for testing."""
    disputes = [
        {
            "id": str(uuid.uuid4()),
            "type": "incorrect_balance",
            "bureau": "experian",
            "creditor_name": "Chase Bank",
            "account_number_last4": "4521",
            "disputed_amount": 1250.00,
            "status": "pending",
            "submitted_at": None,
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "id": str(uuid.uuid4()),
            "type": "not_my_account",
            "bureau": "equifax",
            "creditor_name": "Capital One",
            "account_number_last4": "7832",
            "disputed_amount": 0.00,
            "status": "submitted",
            "submitted_at": (datetime.utcnow() - timedelta(days=15)).isoformat(),
            "created_at": (datetime.utcnow() - timedelta(days=15)).isoformat(),
        },
        {
            "id": str(uuid.uuid4()),
            "type": "late_payment_error",
            "bureau": "transunion",
            "creditor_name": "Discover",
            "account_number_last4": "3301",
            "disputed_amount": 0.00,
            "status": "resolved_favorable",
            "submitted_at": (datetime.utcnow() - timedelta(days=45)).isoformat(),
            "resolved_at": (datetime.utcnow() - timedelta(days=10)).isoformat(),
            "created_at": (datetime.utcnow() - timedelta(days=45)).isoformat(),
        },
    ]
    print(f"  ✅ Sample disputes: {len(disputes)} records ready")
    return disputes


def main():
    """Run all seed operations."""
    print()
    print("=" * 50)

    tiers = seed_subscription_tiers(None)
    clients = seed_test_clients()
    disputes = seed_sample_disputes()

    print()
    print("=" * 50)
    print(f"✅ Seed complete!")
    print(f"   • {len(tiers)} subscription tiers")
    print(f"   • {len(clients)} test clients")
    print(f"   • {len(disputes)} sample disputes")
    print()
    print("NOTE: Wire up DB session to actually insert these once")
    print("      ORM models are defined (see app/models/).")
    print()


if __name__ == "__main__":
    main()
