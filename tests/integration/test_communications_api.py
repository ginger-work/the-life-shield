"""
Integration tests for Communications API endpoints.
Tests consent management, channel history, and webhook handling.
"""
import pytest
import uuid


def test_consent_status_requires_auth(test_client):
    """GET /api/v1/communications/consent/status/{id} requires auth."""
    fake_id = str(uuid.uuid4())
    response = test_client.get(f"/api/v1/communications/consent/status/{fake_id}")
    assert response.status_code == 401


def test_send_sms_requires_admin(test_client, auth_headers):
    """POST /api/v1/communications/sms/send requires admin role."""
    response = test_client.post(
        "/api/v1/communications/sms/send",
        json={"client_id": str(uuid.uuid4()), "message": "Test"},
        headers=auth_headers,
    )
    # Client role should get 403
    assert response.status_code in (403, 404)


def test_sms_webhook_returns_twiml(test_client):
    """POST /api/v1/communications/sms/webhook should return TwiML XML."""
    response = test_client.post(
        "/api/v1/communications/sms/webhook",
        data={
            "From": "+19195550000",
            "Body": "Hello Tim Shaw",
            "SmsSid": "SM123",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    assert "xml" in response.headers.get("content-type", "").lower()


def test_voice_webhook_returns_twiml(test_client):
    """POST /api/v1/communications/voice/webhook returns TwiML."""
    response = test_client.post("/api/v1/communications/voice/webhook")
    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    assert "xml" in content_type.lower()
    assert "Tim Shaw" in response.text


def test_voice_gather_valid_digit(test_client):
    """POST /api/v1/communications/voice/gather responds to digit input."""
    response = test_client.post(
        "/api/v1/communications/voice/gather",
        data={"Digits": "1", "CallSid": "CA123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200


def test_voice_gather_zero_connects_human(test_client):
    """Pressing 0 in voice menu should initiate human transfer."""
    response = test_client.post(
        "/api/v1/communications/voice/gather",
        data={"Digits": "0", "CallSid": "CA123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    assert "Dial" in response.text or "human" in response.text.lower()


def test_email_webhook_returns_success(test_client):
    """POST /api/v1/communications/email/webhook handles inbound email."""
    response = test_client.post(
        "/api/v1/communications/email/webhook",
        json={
            "from": "client@test.com",
            "subject": "Question about dispute",
            "text": "Hi, what is the status of my dispute?",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


def test_chat_message_requires_auth(test_client):
    """POST /api/v1/communications/chat/message requires auth."""
    response = test_client.post(
        "/api/v1/communications/chat/message",
        json={"message": "Hello"},
    )
    assert response.status_code == 401


def test_video_webhook_handles_events(test_client):
    """POST /api/v1/communications/video/webhook handles Zoom events."""
    response = test_client.post(
        "/api/v1/communications/video/webhook",
        json={"event": "meeting.ended", "payload": {}},
    )
    assert response.status_code == 200
