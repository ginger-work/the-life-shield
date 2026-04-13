"""
Integration tests for Agents (Tim Shaw) API endpoints.
"""
import pytest
from unittest.mock import MagicMock, patch


def test_tim_shaw_status_endpoint(test_client):
    """GET /api/v1/agents/status should return availability info."""
    response = test_client.get("/api/v1/agents/status")
    assert response.status_code == 200
    data = response.json()
    assert "agent" in data
    assert data["agent"] == "Tim Shaw"
    assert "status" in data
    assert "channels" in data
    assert "disclosure" in data
    assert "AI" in data["disclosure"] or "AI agent" in data["disclosure"]


def test_chat_requires_auth(test_client):
    """POST /api/v1/agents/chat should require authentication."""
    response = test_client.post("/api/v1/agents/chat", json={"message": "Hello"})
    assert response.status_code == 401


def test_chat_empty_message_returns_400(test_client, auth_headers_with_profile):
    """Empty chat message should return 400."""
    response = test_client.post(
        "/api/v1/agents/chat",
        json={"message": "   "},
        headers=auth_headers_with_profile,
    )
    assert response.status_code == 400


def test_escalate_requires_auth(test_client):
    """POST /api/v1/agents/escalate should require authentication."""
    response = test_client.post(
        "/api/v1/agents/escalate",
        json={"reason": "complaint"},
    )
    assert response.status_code == 401


def test_agent_status_has_ai_disclosure(test_client):
    """Agent status must include AI disclosure for compliance."""
    response = test_client.get("/api/v1/agents/status")
    assert response.status_code == 200
    data = response.json()
    disclosure = data.get("disclosure", "")
    assert len(disclosure) > 0, "AI disclosure must be present"


def test_chat_history_requires_auth(test_client):
    """Conversation history should require authentication."""
    import uuid
    fake_client_id = str(uuid.uuid4())
    response = test_client.get(f"/api/v1/agents/history/{fake_client_id}")
    assert response.status_code == 401
