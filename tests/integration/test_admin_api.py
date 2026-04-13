"""
Integration tests for Admin Back Office API endpoints.
"""
import pytest
import uuid


def test_admin_list_clients_requires_admin(test_client, auth_headers):
    """GET /api/v1/admin/clients requires admin role."""
    response = test_client.get("/api/v1/admin/clients", headers=auth_headers)
    assert response.status_code == 403


def test_admin_list_clients_unauthenticated_returns_401(test_client):
    """GET /api/v1/admin/clients requires auth."""
    response = test_client.get("/api/v1/admin/clients")
    assert response.status_code == 401


def test_admin_analytics_overview_requires_admin(test_client, auth_headers):
    """GET /api/v1/admin/analytics/overview requires admin role."""
    response = test_client.get("/api/v1/admin/analytics/overview", headers=auth_headers)
    assert response.status_code == 403


def test_admin_dispute_stats_requires_admin(test_client, auth_headers):
    """GET /api/v1/admin/disputes/stats requires admin role."""
    response = test_client.get("/api/v1/admin/disputes/stats", headers=auth_headers)
    assert response.status_code == 403


def test_admin_list_agents_requires_admin(test_client, auth_headers):
    """GET /api/v1/admin/agents requires admin role."""
    response = test_client.get("/api/v1/admin/agents", headers=auth_headers)
    assert response.status_code == 403


def test_admin_override_takeover_requires_admin(test_client, auth_headers):
    """POST /api/v1/admin/override/takeover/{id} requires admin role."""
    fake_id = str(uuid.uuid4())
    response = test_client.post(
        f"/api/v1/admin/override/takeover/{fake_id}",
        json={"note": "test"},
        headers=auth_headers,
    )
    assert response.status_code == 403


def test_admin_active_takeovers_requires_admin(test_client, auth_headers):
    """GET /api/v1/admin/override/active requires admin role."""
    response = test_client.get("/api/v1/admin/override/active", headers=auth_headers)
    assert response.status_code == 403


def test_admin_billing_subscriptions_requires_admin(test_client, auth_headers):
    """GET /api/v1/admin/billing/subscriptions requires admin role."""
    response = test_client.get("/api/v1/admin/billing/subscriptions", headers=auth_headers)
    assert response.status_code == 403


def test_admin_revenue_requires_admin(test_client, auth_headers):
    """GET /api/v1/admin/billing/revenue requires admin role."""
    response = test_client.get("/api/v1/admin/billing/revenue", headers=auth_headers)
    assert response.status_code == 403


def test_admin_broadcast_requires_admin(test_client, auth_headers):
    """POST /api/v1/admin/override/broadcast requires admin role."""
    response = test_client.post(
        "/api/v1/admin/override/broadcast",
        json={"message": "System update tonight", "channel": "portal_chat"},
        headers=auth_headers,
    )
    assert response.status_code == 403
