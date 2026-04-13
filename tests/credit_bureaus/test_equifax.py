"""
Tests for api.credit_bureaus.equifax — EquifaxClient

Coverage target: 80%+

Approach:
- All HTTP calls are mocked with unittest.mock.patch (no live requests)
- Tests cover success paths, validation errors, auth failures,
  rate limits, network timeouts, and response normalisation
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from api.credit_bureaus.equifax import EquifaxClient
from api.credit_bureaus.base import (
    AuthenticationError,
    CreditBureauError,
    DisputeError,
    ReportPullError,
    ValidationError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_CONSUMER = {
    "ssn": "123-45-6789",
    "dob": "1985-03-17",
    "first_name": "John",
    "last_name": "Smith",
    "address": {
        "line1": "123 Main St",
        "city": "Charlotte",
        "state": "NC",
        "zip": "28201",
    },
}

MINIMAL_CONSUMER = {
    "ssn": "123-45-6789",
    "dob": "1985-03-17",
    "first_name": "John",
    "last_name": "Smith",
}

CLIENT_CONFIG = {
    "client_id": "test-client-id",
    "client_secret": "test-client-secret",
    "org_id": "test-org-id",
    "base_url": "https://api.sandbox.equifax.com/business/credit-reports/v1",
    "token_url": "https://api.sandbox.equifax.com/v2/oauth/token",
    "sandbox": True,
    "timeout": 10,
    "max_retries": 1,
}

MOCK_TOKEN_RESPONSE = {
    "access_token": "mock-access-token-abc123",
    "token_type": "Bearer",
    "expires_in": 3600,
}

MOCK_REPORT_RESPONSE = {
    "consumerCreditReport": [
        {
            "scoreCard": [{"score": {"results": 712}}],
            "tradelines": [
                {
                    "accountNumber": "xxxx1234",
                    "creditorName": "Chase Bank",
                    "balance": 2500,
                    "status": "Current",
                }
            ],
            "inquiries": [
                {"creditorName": "Capitol One", "date": "2026-01-15"}
            ],
            "bankruptcies": [],
            "disputes": [],
            "collections": [],
        }
    ]
}

MOCK_DISPUTE_RESPONSE = {
    "caseNumber": "EQ-2026-001234",
    "status": "FILED",
    "message": "Dispute filed successfully",
}

MOCK_STATUS_RESPONSE = {
    "caseNumber": "EQ-2026-001234",
    "status": "IN_PROGRESS",
    "lastUpdated": "2026-04-13T18:00:00Z",
    "expectedResolutionDate": "2026-05-13T00:00:00Z",
    "resolution": None,
}

MOCK_CHANGES_RESPONSE = {
    "changes": [
        {"type": "new_inquiry", "date": "2026-04-10", "creditor": "Discover"}
    ]
}


def _make_mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock requests.Response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.text = str(json_data)
    return mock


def _make_client_with_token() -> EquifaxClient:
    """Return a pre-authenticated EquifaxClient."""
    client = EquifaxClient(CLIENT_CONFIG)
    client._token = "mock-access-token-abc123"
    client._token_expiry = time.time() + 3600
    return client


# ---------------------------------------------------------------------------
# Authentication tests
# ---------------------------------------------------------------------------

class TestAuthentication:

    def test_authenticate_success(self):
        client = EquifaxClient(CLIENT_CONFIG)
        mock_resp = _make_mock_response(MOCK_TOKEN_RESPONSE)

        with patch("requests.post", return_value=mock_resp):
            token = client._authenticate()

        assert token == "mock-access-token-abc123"
        assert client._token_expiry > time.time()

    def test_authenticate_failure_bad_status(self):
        client = EquifaxClient(CLIENT_CONFIG)
        mock_resp = _make_mock_response({}, status_code=401)

        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(AuthenticationError, match="token request failed"):
                client._authenticate()

    def test_authenticate_missing_token_in_response(self):
        client = EquifaxClient(CLIENT_CONFIG)
        mock_resp = _make_mock_response({"error": "invalid_client"})

        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(AuthenticationError, match="missing access_token"):
                client._authenticate()

    def test_authenticate_network_error(self):
        client = EquifaxClient(CLIENT_CONFIG)

        with patch("requests.post", side_effect=requests.exceptions.ConnectionError("refused")):
            with pytest.raises(AuthenticationError, match="network error"):
                client._authenticate()

    def test_token_refresh_on_expiry(self):
        client = EquifaxClient(CLIENT_CONFIG)
        # Set token as expired
        client._token = "old-token"
        client._token_expiry = time.time() - 100

        mock_token_resp = _make_mock_response(MOCK_TOKEN_RESPONSE)
        mock_report_resp = _make_mock_response(MOCK_REPORT_RESPONSE)

        with patch("requests.post", return_value=mock_token_resp):
            with patch.object(client._session, "request", return_value=mock_report_resp):
                client.pull_credit_report("client-001", VALID_CONSUMER)

        assert client._token == "mock-access-token-abc123"


# ---------------------------------------------------------------------------
# Pull credit report tests
# ---------------------------------------------------------------------------

class TestPullCreditReport:

    def test_pull_report_success(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response(MOCK_REPORT_RESPONSE)

        with patch.object(client._session, "request", return_value=mock_resp):
            result = client.pull_credit_report("client-001", VALID_CONSUMER)

        assert result["bureau"] == "equifax"
        assert result["client_id"] == "client-001"
        assert result["score"] == 712
        assert len(result["tradelines"]) == 1
        assert len(result["inquiries"]) == 1
        assert result["public_records"] == []
        assert result["raw"] == MOCK_REPORT_RESPONSE

    def test_pull_report_normalises_missing_score(self):
        client = _make_client_with_token()
        empty_report = {"consumerCreditReport": [{}]}
        mock_resp = _make_mock_response(empty_report)

        with patch.object(client._session, "request", return_value=mock_resp):
            result = client.pull_credit_report("client-001", VALID_CONSUMER)

        assert result["score"] is None

    def test_pull_report_missing_required_field_ssn(self):
        client = _make_client_with_token()
        consumer = {k: v for k, v in VALID_CONSUMER.items() if k != "ssn"}

        with pytest.raises(ValidationError, match="ssn"):
            client.pull_credit_report("client-001", consumer)

    def test_pull_report_missing_address_field(self):
        client = _make_client_with_token()
        consumer = {**VALID_CONSUMER, "address": {"line1": "123 Main"}}  # missing city/state/zip

        with pytest.raises(ValidationError, match="city"):
            client.pull_credit_report("client-001", consumer)

    def test_pull_report_api_error_raises_report_pull_error(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response({"error": "server_error"}, status_code=500)

        with patch.object(client._session, "request", return_value=mock_resp):
            with pytest.raises(ReportPullError):
                client.pull_credit_report("client-001", VALID_CONSUMER)

    def test_pull_report_401_raises_report_pull_error_with_auth_cause(self):
        """A 401 during report pull wraps as ReportPullError (caused by AuthenticationError)."""
        client = _make_client_with_token()
        mock_resp = _make_mock_response({}, status_code=401)

        with patch.object(client._session, "request", return_value=mock_resp):
            with pytest.raises(ReportPullError, match="authentication"):
                client.pull_credit_report("client-001", VALID_CONSUMER)

    def test_pull_report_timeout_raises_credit_bureau_error(self):
        client = _make_client_with_token()

        with patch.object(
            client._session, "request",
            side_effect=requests.exceptions.Timeout("timed out")
        ):
            with pytest.raises(CreditBureauError, match="timed out"):
                client.pull_credit_report("client-001", VALID_CONSUMER)

    def test_pull_report_ssn_dashes_stripped(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response(MOCK_REPORT_RESPONSE)
        captured_payloads = []

        def capture_request(method, url, **kwargs):
            captured_payloads.append(kwargs.get("json", {}))
            return mock_resp

        with patch.object(client._session, "request", side_effect=capture_request):
            client.pull_credit_report("client-001", VALID_CONSUMER)

        ssn_in_payload = (
            captured_payloads[0]
            .get("consumers", {})
            .get("socialNum", [{}])[0]
            .get("number", "")
        )
        assert "-" not in ssn_in_payload


# ---------------------------------------------------------------------------
# Dispute filing tests
# ---------------------------------------------------------------------------

class TestFileDispute:

    def test_file_dispute_success(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response(MOCK_DISPUTE_RESPONSE)

        with patch.object(client._session, "request", return_value=mock_resp):
            result = client.file_dispute(
                "client-001",
                MINIMAL_CONSUMER,
                item_id="TL-12345",
                reason="NOT_MY_ACCOUNT",
                statement="This account does not belong to me.",
            )

        assert result["bureau"] == "equifax"
        assert result["case_number"] == "EQ-2026-001234"
        assert result["item_id"] == "TL-12345"
        assert result["status"] == "FILED"
        assert "filed_at" in result
        assert "expected_resolution_date" in result

    def test_file_dispute_missing_case_number(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response({"status": "OK"})  # no caseNumber

        with patch.object(client._session, "request", return_value=mock_resp):
            # The base class _require_fields will raise ValidationError
            with pytest.raises((ValidationError, DisputeError)):
                client.file_dispute(
                    "client-001", MINIMAL_CONSUMER, "TL-99", "INACCURATE_INFO"
                )

    def test_file_dispute_api_error(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response({}, status_code=422)

        with patch.object(client._session, "request", return_value=mock_resp):
            with pytest.raises(DisputeError):
                client.file_dispute(
                    "client-001", MINIMAL_CONSUMER, "TL-99", "INACCURATE_INFO"
                )

    def test_file_dispute_without_statement(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response(MOCK_DISPUTE_RESPONSE)
        captured_payloads = []

        def capture(method, url, **kwargs):
            captured_payloads.append(kwargs.get("json", {}))
            return mock_resp

        with patch.object(client._session, "request", side_effect=capture):
            client.file_dispute("client-001", MINIMAL_CONSUMER, "TL-99", "WRONG_AMOUNT")

        statement_in_payload = (
            captured_payloads[0]
            .get("disputedItems", [{}])[0]
            .get("consumerStatement", "sentinel")
        )
        assert statement_in_payload == ""


# ---------------------------------------------------------------------------
# Dispute status tests
# ---------------------------------------------------------------------------

class TestGetDisputeStatus:

    def test_get_dispute_status_success(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response(MOCK_STATUS_RESPONSE)

        with patch.object(client._session, "request", return_value=mock_resp):
            result = client.get_dispute_status(
                "client-001", "EQ-2026-001234", "123-45-6789"
            )

        assert result["case_number"] == "EQ-2026-001234"
        assert result["status"] == "IN_PROGRESS"
        assert result["bureau"] == "equifax"

    def test_get_dispute_status_missing_status_field(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response({"caseNumber": "EQ-123"})  # no "status"

        with patch.object(client._session, "request", return_value=mock_resp):
            with pytest.raises(ValidationError, match="status"):
                client.get_dispute_status("client-001", "EQ-123", "123456789")

    def test_get_dispute_status_ssn_dashes_stripped(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response(MOCK_STATUS_RESPONSE)
        captured_params = []

        def capture(method, url, **kwargs):
            captured_params.append(kwargs.get("params", {}))
            return mock_resp

        with patch.object(client._session, "request", side_effect=capture):
            client.get_dispute_status("client-001", "EQ-123", "123-45-6789")

        assert "-" not in captured_params[0].get("ssn", "")


# ---------------------------------------------------------------------------
# Monitor changes tests
# ---------------------------------------------------------------------------

class TestMonitorChanges:

    def test_monitor_changes_success(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response(MOCK_CHANGES_RESPONSE)

        with patch.object(client._session, "request", return_value=mock_resp):
            result = client.monitor_changes("client-001", "123-45-6789")

        assert result["bureau"] == "equifax"
        assert result["change_count"] == 1
        assert result["changes"][0]["type"] == "new_inquiry"

    def test_monitor_changes_empty(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response({"changes": []})

        with patch.object(client._session, "request", return_value=mock_resp):
            result = client.monitor_changes("client-001", "123456789")

        assert result["change_count"] == 0
        assert result["changes"] == []


# ---------------------------------------------------------------------------
# Health check tests
# ---------------------------------------------------------------------------

class TestHealthCheck:

    def test_health_check_success(self):
        client = _make_client_with_token()
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch.object(client._session, "get", return_value=mock_resp):
            assert client.health_check() is True

    def test_health_check_failure(self):
        client = _make_client_with_token()
        mock_resp = MagicMock()
        mock_resp.status_code = 503

        with patch.object(client._session, "get", return_value=mock_resp):
            assert client.health_check() is False

    def test_health_check_network_error_returns_false(self):
        client = _make_client_with_token()

        with patch.object(
            client._session, "get",
            side_effect=requests.exceptions.ConnectionError("refused")
        ):
            assert client.health_check() is False


# ---------------------------------------------------------------------------
# Rate limiting tests
# ---------------------------------------------------------------------------

class TestRateLimiting:

    def test_rate_limit_enforced(self):
        """Verify rate limiting does not crash and processes requests."""
        config = {**CLIENT_CONFIG, "rate_limit_per_minute": 5}
        client = EquifaxClient(config)
        client._token = "mock-token"
        client._token_expiry = time.time() + 3600

        mock_resp = _make_mock_response(MOCK_REPORT_RESPONSE)
        call_count = 0

        def mock_request(method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_resp

        with patch.object(client._session, "request", side_effect=mock_request):
            # First 5 should not sleep (within limit)
            for _ in range(5):
                client.pull_credit_report("client-001", VALID_CONSUMER)

        assert call_count == 5


# ---------------------------------------------------------------------------
# from_env factory tests
# ---------------------------------------------------------------------------

class TestFromEnv:

    def test_from_env_success(self, monkeypatch):
        monkeypatch.setenv("EQUIFAX_CLIENT_ID", "env-client-id")
        monkeypatch.setenv("EQUIFAX_CLIENT_SECRET", "env-secret")
        monkeypatch.setenv("EQUIFAX_ORG_ID", "env-org-id")
        monkeypatch.setenv("EQUIFAX_SANDBOX", "true")

        client = EquifaxClient.from_env()
        assert client._client_id == "env-client-id"
        assert client.sandbox is True

    def test_from_env_missing_required_var(self, monkeypatch):
        monkeypatch.delenv("EQUIFAX_CLIENT_ID", raising=False)
        monkeypatch.delenv("EQUIFAX_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("EQUIFAX_ORG_ID", raising=False)

        with pytest.raises(KeyError):
            EquifaxClient.from_env()
