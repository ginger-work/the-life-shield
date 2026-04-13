"""
Tests for api.credit_bureaus.transunion — TransUnionClient

Coverage target: 80%+
"""

from __future__ import annotations

import hashlib
import hmac
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from api.credit_bureaus.transunion import TransUnionClient
from api.credit_bureaus.base import (
    AuthenticationError,
    CreditBureauError,
    DisputeError,
    ReportPullError,
    ValidationError,
)


VALID_CONSUMER = {
    "ssn": "111-22-3333",
    "dob": "1975-11-20",
    "first_name": "Marcus",
    "last_name": "Johnson",
    "address": {
        "line1": "789 Pine Blvd",
        "city": "Durham",
        "state": "NC",
        "zip": "27701",
    },
}

MINIMAL_CONSUMER = {
    "ssn": "111-22-3333",
    "dob": "1975-11-20",
    "first_name": "Marcus",
    "last_name": "Johnson",
}

CLIENT_CONFIG = {
    "api_key": "tu-test-api-key",
    "api_secret": "tu-test-api-secret",
    "base_url": "https://apitest.transunion.com/credit-reports/v1",
    "token_url": "https://apitest.transunion.com/auth/v1/token",
    "sandbox": True,
    "timeout": 10,
    "max_retries": 1,
}

MOCK_TOKEN_RESPONSE = {
    "accessToken": "tu-bearer-token-abc",
    "expiresIn": 3600,
}

MOCK_REPORT_RESPONSE = {
    "creditReport": {
        "product": [{
            "scoreModel": [{"score": {"results": 688}}],
            "tradeline": [
                {"accountNumber": "xxxx9999", "creditorName": "Bank of America"}
            ],
            "inquiry": [{"creditorName": "Discover", "date": "2026-03-01"}],
            "publicRecord": [],
            "dispute": [],
            "collection": [],
        }]
    }
}

MOCK_DISPUTE_RESPONSE = {
    "confirmationNumber": "TU-2026-005678",
    "status": "FILED",
}

MOCK_STATUS_RESPONSE = {
    "status": "INVESTIGATING",
    "lastUpdated": "2026-04-12T10:00:00Z",
    "expectedResolutionDate": "2026-05-12T00:00:00Z",
}

MOCK_CHANGES_RESPONSE = {
    "creditFileChanges": [
        {"type": "new_account", "date": "2026-04-05", "creditor": "Citi"}
    ]
}


def _mock_resp(json_data: dict, status_code: int = 200) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.text = str(json_data)
    return mock


def _authed_client() -> TransUnionClient:
    client = TransUnionClient(CLIENT_CONFIG)
    client._token = "tu-bearer-token-abc"
    client._token_expiry = time.time() + 3600
    return client


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class TestAuthentication:

    def test_authenticate_success(self):
        client = TransUnionClient(CLIENT_CONFIG)
        mock = _mock_resp(MOCK_TOKEN_RESPONSE)

        with patch("requests.post", return_value=mock):
            token = client._authenticate()

        assert token == "tu-bearer-token-abc"

    def test_authenticate_uses_hmac_signature(self):
        client = TransUnionClient(CLIENT_CONFIG)
        mock = _mock_resp(MOCK_TOKEN_RESPONSE)
        captured = []

        def capture_post(url, **kwargs):
            captured.append(kwargs.get("json", {}))
            return mock

        with patch("requests.post", side_effect=capture_post):
            client._authenticate()

        payload = captured[0]
        assert payload["apiKey"] == "tu-test-api-key"
        assert "signature" in payload
        assert "timestamp" in payload

        # Verify the signature matches
        ts = payload["timestamp"]
        expected = hmac.new(
            b"tu-test-api-secret",
            f"tu-test-api-key:{ts}".encode(),
            hashlib.sha256,
        ).hexdigest()
        assert payload["signature"] == expected

    def test_authenticate_failure(self):
        client = TransUnionClient(CLIENT_CONFIG)
        mock = _mock_resp({}, status_code=401)

        with patch("requests.post", return_value=mock):
            with pytest.raises(AuthenticationError, match="failed"):
                client._authenticate()

    def test_authenticate_missing_access_token(self):
        client = TransUnionClient(CLIENT_CONFIG)
        mock = _mock_resp({"status": "OK"})

        with patch("requests.post", return_value=mock):
            with pytest.raises(AuthenticationError, match="missing accessToken"):
                client._authenticate()

    def test_authenticate_network_error(self):
        client = TransUnionClient(CLIENT_CONFIG)

        with patch("requests.post", side_effect=requests.exceptions.ConnectionError()):
            with pytest.raises(AuthenticationError, match="network error"):
                client._authenticate()

    def test_authenticate_fallback_access_token_key(self):
        """TransUnion may use 'access_token' instead of 'accessToken'."""
        client = TransUnionClient(CLIENT_CONFIG)
        mock = _mock_resp({"access_token": "alt-token", "expires_in": 1800})

        with patch("requests.post", return_value=mock):
            token = client._authenticate()

        assert token == "alt-token"


# ---------------------------------------------------------------------------
# Pull credit report
# ---------------------------------------------------------------------------

class TestPullCreditReport:

    def test_pull_report_success(self):
        client = _authed_client()
        mock = _mock_resp(MOCK_REPORT_RESPONSE)

        with patch.object(client._session, "request", return_value=mock):
            result = client.pull_credit_report("client-003", VALID_CONSUMER)

        assert result["bureau"] == "transunion"
        assert result["score"] == 688
        assert len(result["tradelines"]) == 1
        assert len(result["inquiries"]) == 1

    def test_pull_report_empty_product(self):
        client = _authed_client()
        mock = _mock_resp({"creditReport": {"product": [{}]}})

        with patch.object(client._session, "request", return_value=mock):
            result = client.pull_credit_report("client-003", VALID_CONSUMER)

        assert result["score"] is None
        assert result["tradelines"] == []

    def test_pull_report_missing_ssn(self):
        client = _authed_client()
        consumer = {k: v for k, v in VALID_CONSUMER.items() if k != "ssn"}

        with pytest.raises(ValidationError):
            client.pull_credit_report("client-003", consumer)

    def test_pull_report_missing_address_field(self):
        client = _authed_client()
        consumer = {**VALID_CONSUMER, "address": {"line1": "789 Pine"}}

        with pytest.raises(ValidationError, match="city"):
            client.pull_credit_report("client-003", consumer)

    def test_pull_report_api_error(self):
        client = _authed_client()
        mock = _mock_resp({}, status_code=500)

        with patch.object(client._session, "request", return_value=mock):
            with pytest.raises(ReportPullError):
                client.pull_credit_report("client-003", VALID_CONSUMER)

    def test_pull_report_timeout(self):
        client = _authed_client()

        with patch.object(
            client._session, "request",
            side_effect=requests.exceptions.Timeout()
        ):
            with pytest.raises(CreditBureauError, match="timed out"):
                client.pull_credit_report("client-003", VALID_CONSUMER)


# ---------------------------------------------------------------------------
# Dispute filing
# ---------------------------------------------------------------------------

class TestFileDispute:

    def test_file_dispute_success(self):
        client = _authed_client()
        mock = _mock_resp(MOCK_DISPUTE_RESPONSE)

        with patch.object(client._session, "request", return_value=mock):
            result = client.file_dispute(
                "client-003", MINIMAL_CONSUMER,
                item_id="TU-TL-001", reason="NOT_MY_ACCOUNT",
            )

        assert result["bureau"] == "transunion"
        assert result["case_number"] == "TU-2026-005678"
        assert result["status"] == "FILED"

    def test_file_dispute_missing_confirmation_number(self):
        client = _authed_client()
        mock = _mock_resp({"status": "OK"})

        with patch.object(client._session, "request", return_value=mock):
            with pytest.raises(DisputeError, match="missing confirmation"):
                client.file_dispute(
                    "client-003", MINIMAL_CONSUMER, "TL-1", "WRONG"
                )

    def test_file_dispute_api_error(self):
        client = _authed_client()
        mock = _mock_resp({}, status_code=422)

        with patch.object(client._session, "request", return_value=mock):
            with pytest.raises(DisputeError):
                client.file_dispute(
                    "client-003", MINIMAL_CONSUMER, "TL-1", "REASON"
                )


# ---------------------------------------------------------------------------
# Dispute status
# ---------------------------------------------------------------------------

class TestGetDisputeStatus:

    def test_get_status_success(self):
        client = _authed_client()
        mock = _mock_resp(MOCK_STATUS_RESPONSE)

        with patch.object(client._session, "request", return_value=mock):
            result = client.get_dispute_status("client-003", "TU-123", "111223333")

        assert result["status"] == "INVESTIGATING"
        assert result["bureau"] == "transunion"

    def test_get_status_missing_status_field(self):
        client = _authed_client()
        mock = _mock_resp({"lastUpdated": "2026-04-01"})

        with patch.object(client._session, "request", return_value=mock):
            with pytest.raises(ValidationError, match="status"):
                client.get_dispute_status("client-003", "TU-123", "111223333")


# ---------------------------------------------------------------------------
# Monitor changes
# ---------------------------------------------------------------------------

class TestMonitorChanges:

    def test_monitor_changes_returns_changes(self):
        client = _authed_client()
        mock = _mock_resp(MOCK_CHANGES_RESPONSE)

        with patch.object(client._session, "request", return_value=mock):
            result = client.monitor_changes("client-003", "111223333")

        assert result["change_count"] == 1
        assert result["changes"][0]["type"] == "new_account"

    def test_monitor_changes_empty(self):
        client = _authed_client()
        mock = _mock_resp({"changes": []})

        with patch.object(client._session, "request", return_value=mock):
            result = client.monitor_changes("client-003", "111223333")

        assert result["change_count"] == 0


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealthCheck:

    def test_health_check_success(self):
        client = _authed_client()
        mock = MagicMock(status_code=200)

        with patch.object(client._session, "get", return_value=mock):
            assert client.health_check() is True

    def test_health_check_failure(self):
        client = _authed_client()

        with patch.object(
            client._session, "get",
            side_effect=requests.exceptions.ConnectionError()
        ):
            assert client.health_check() is False


# ---------------------------------------------------------------------------
# from_env
# ---------------------------------------------------------------------------

class TestFromEnv:

    def test_from_env_success(self, monkeypatch):
        monkeypatch.setenv("TRANSUNION_API_KEY", "env-key")
        monkeypatch.setenv("TRANSUNION_API_SECRET", "env-secret")
        monkeypatch.setenv("TRANSUNION_SANDBOX", "true")

        client = TransUnionClient.from_env()
        assert client._api_key == "env-key"
        assert client.sandbox is True

    def test_from_env_missing_required(self, monkeypatch):
        monkeypatch.delenv("TRANSUNION_API_KEY", raising=False)
        monkeypatch.delenv("TRANSUNION_API_SECRET", raising=False)

        with pytest.raises(KeyError):
            TransUnionClient.from_env()
