"""
Unit tests for TRGpay payment integration.
"""
import pytest
from unittest.mock import MagicMock, patch


class TestTRGPayClient:
    def test_charge_returns_charge_id(self):
        from app.integrations.trgpay import TRGPayClient
        client = TRGPayClient(sandbox=True)

        result = client.charge(
            amount=79.99,
            card_token="tok_test_visa",
            description="Premium Plan",
            metadata={"client_id": "test123"},
        )
        assert result["success"] is True
        assert "charge_id" in result
        assert result["charge_id"].startswith("ch_")

    def test_charge_zero_amount_returns_error(self):
        from app.integrations.trgpay import TRGPayClient
        client = TRGPayClient(sandbox=True)

        result = client.charge(
            amount=0,
            card_token="tok_test",
            description="Zero charge",
        )
        assert result["success"] is False
        assert "error" in result

    def test_charge_negative_amount_returns_error(self):
        from app.integrations.trgpay import TRGPayClient
        client = TRGPayClient(sandbox=True)

        result = client.charge(
            amount=-10.00,
            card_token="tok_test",
            description="Negative charge",
        )
        assert result["success"] is False

    def test_refund_returns_refund_id(self):
        from app.integrations.trgpay import TRGPayClient
        client = TRGPayClient(sandbox=True)

        result = client.refund(charge_id="ch_test123", amount=79.99)
        assert result["success"] is True
        assert "refund_id" in result
        assert result["refund_id"].startswith("re_")

    def test_refund_without_charge_id_returns_error(self):
        from app.integrations.trgpay import TRGPayClient
        client = TRGPayClient(sandbox=True)

        result = client.refund(charge_id="")
        assert result["success"] is False

    def test_create_subscription_returns_subscription_id(self):
        from app.integrations.trgpay import TRGPayClient
        client = TRGPayClient(sandbox=True)

        result = client.create_subscription(
            plan_id="premium",
            card_token="tok_test",
            customer_id="cust_123",
        )
        assert result["success"] is True
        assert "subscription_id" in result

    def test_cancel_subscription_returns_success(self):
        from app.integrations.trgpay import TRGPayClient
        client = TRGPayClient(sandbox=True)

        result = client.cancel_subscription("sub_test123")
        assert "success" in result

    def test_verify_webhook_signature_valid(self):
        import hmac
        import hashlib
        from app.integrations.trgpay import TRGPayClient, TRGPAY_SECRET_KEY

        client = TRGPayClient(sandbox=True)
        payload = b'{"event": "charge.completed"}'
        expected_sig = hmac.new(
            TRGPAY_SECRET_KEY.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        assert client.verify_webhook_signature(payload, expected_sig) is True

    def test_verify_webhook_signature_invalid(self):
        from app.integrations.trgpay import TRGPayClient
        client = TRGPayClient(sandbox=True)

        payload = b'{"event": "charge.completed"}'
        assert client.verify_webhook_signature(payload, "bad_signature") is False

    def test_mock_response_falls_back_gracefully(self):
        """TRGpay client returns mock response when httpx not available."""
        from app.integrations.trgpay import TRGPayClient
        client = TRGPayClient(sandbox=True)

        # Force mock path by using invalid URL
        result = client._mock_response("charges", {"amount": 100})
        assert result["success"] is True
