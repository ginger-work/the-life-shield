"""
Tests for api.credit_bureaus.experian — ExperianClient

Coverage target: 80%+
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from api.credit_bureaus.experian import ExperianClient
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
    "ssn": "987-65-4321",
    "dob": "1990-07-04",
    "first_name": "Jane",
    "last_name": "Doe",
    "address": {
        "line1": "456 Oak Ave",
        "city": "Raleigh",
        "state": "NC",
        "zip": "27601",
    },
}

MINIMAL_CONSUMER = {
    "ssn": "987-65-4321",
    "dob": "1990-07-04",
    "first_name": "Jane",
    "last_name": "Doe",
}

CLIENT_CONFIG = {
    "client_id": "exp-client-id",
    "client_secret": "exp-client-secret",
    "base_url": "https://sandbox.experian.com/consumerservices/credit-profile/v2",
    "token_url": "https://sandbox.experian.com/oauth2/v1/token",
    "sandbox": True,
    "timeout": 10,
    "max_retries": 1,
}

MOCK_TOKEN_RESPONSE = {
    "access_token": "experian-token-xyz789",
    "expires_in": 1800,
}

MOCK_REPORT_RESPONSE = {
    "creditProfile": [
        {
            "riskModel": [{"score": 755}],
            "tradeline": [
                {"accountNumber": "xxxx5678", "creditorName": "Wells Fargo"}
            ],
            "inquiry": [{"creditorName": "Amazon", "date": "2026-02-20"}],
            "publicRecord": [],
            "dispute": [],
            "collection": [],
        }
    ]
}

MOCK_DISPUTE_RESPONSE = {
    "disputeCaseNumber": "EX-2026-007890",
    "status": "SUBMITTED",
}

MOCK_STATUS_RESPONSE = {
    "status": "UNDER_REVIEW",
    "lastUpdatedDate": "2026-04-12T12:00:00Z",
    "expectedCompletionDate": "2026-05-12T00:00:00Z",
}

MOCK_CHANGES_RESPONSE = {
    "alerts": [
        {"type": "score_change", "previous": 740, "current": 755, "date": "2026-04-01"}
    ]
}


def _make_mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.text = str(json_data)
    return mock


def _make_client_with_token() -> ExperianClient:
    client = ExperianClient(CLIENT_CONFIG)
    client._token = "experian-token-xyz789"
    client._token_expiry = time.time() + 1800
    return client


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class TestAuthentication:

    def test_authenticate_success(self):
        client = ExperianClient(CLIENT_CONFIG)
        mock_resp = _make_mock_response(MOCK_TOKEN_RESPONSE)

        with patch("requests.post", return_value=mock_resp):
            token = client._authenticate()

        assert token == "experian-token-xyz789"
        assert client._token_expiry > time.time()

    def test_authenticate_failure(self):
        client = ExperianClient(CLIENT_CONFIG)
        mock_resp = _make_mock_response({}, status_code=403)

        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(AuthenticationError, match="failed"):
                client._authenticate()

    def test_authenticate_missing_access_token(self):
        client = ExperianClient(CLIENT_CONFIG)
        mock_resp = _make_mock_response({"token_type": "Bearer"})

        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(AuthenticationError, match="missing access_token"):
                client._authenticate()

    def test_authenticate_network_error(self):
        client = ExperianClient(CLIENT_CONFIG)

        with patch("requests.post", side_effect=requests.exceptions.ConnectionError()):
            with pytest.raises(AuthenticationError, match="network error"):
                client._authenticate()


# ---------------------------------------------------------------------------
# Pull credit report
# ---------------------------------------------------------------------------

class TestPullCreditReport:

    def test_pull_report_success(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response(MOCK_REPORT_RESPONSE)

        with patch.object(client._session, "request", return_value=mock_resp):
            result = client.pull_credit_report("client-002", VALID_CONSUMER)

        assert result["bureau"] == "experian"
        assert result["client_id"] == "client-002"
        assert result["score"] == 755
        assert len(result["tradelines"]) == 1
        assert result["public_records"] == []

    def test_pull_report_normalises_empty_profile(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response({"creditProfile": [{}]})

        with patch.object(client._session, "request", return_value=mock_resp):
            result = client.pull_credit_report("client-002", VALID_CONSUMER)

        assert result["score"] is None
        assert result["tradelines"] == []

    def test_pull_report_missing_ssn(self):
        client = _make_client_with_token()
        consumer = {k: v for k, v in VALID_CONSUMER.items() if k != "ssn"}

        with pytest.raises(ValidationError):
            client.pull_credit_report("client-002", consumer)

    def test_pull_report_missing_dob(self):
        client = _make_client_with_token()
        consumer = {k: v for k, v in VALID_CONSUMER.items() if k != "dob"}

        with pytest.raises(ValidationError):
            client.pull_credit_report("client-002", consumer)

    def test_pull_report_api_server_error(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response({}, status_code=503)

        with patch.object(client._session, "request", return_value=mock_resp):
            with pytest.raises(ReportPullError):
                client.pull_credit_report("client-002", VALID_CONSUMER)

    def test_pull_report_timeout(self):
        client = _make_client_with_token()

        with patch.object(
            client._session, "request",
            side_effect=requests.exceptions.Timeout()
        ):
            with pytest.raises(CreditBureauError, match="timed out"):
                client.pull_credit_report("client-002", VALID_CONSUMER)

    def test_pull_report_ssn_sanitised(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response(MOCK_REPORT_RESPONSE)
        payloads = []

        def capture(method, url, **kwargs):
            payloads.append(kwargs.get("json", {}))
            return mock_resp

        with patch.object(client._session, "request", side_effect=capture):
            client.pull_credit_report("client-002", VALID_CONSUMER)

        ssn_in_payload = (
            payloads[0]
            .get("consumerPii", {})
            .get("primaryApplicant", {})
            .get("ssn", {})
            .get("full", "")
        )
        assert "-" not in ssn_in_payload
        assert ssn_in_payload == "987654321"


# ---------------------------------------------------------------------------
# File dispute
# ---------------------------------------------------------------------------

class TestFileDispute:

    def test_file_dispute_success(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response(MOCK_DISPUTE_RESPONSE)

        with patch.object(client._session, "request", return_value=mock_resp):
            result = client.file_dispute(
                "client-002",
                MINIMAL_CONSUMER,
                item_id="EX-TL-99",
                reason="INACCURATE_BALANCE",
            )

        assert result["bureau"] == "experian"
        assert result["case_number"] == "EX-2026-007890"
        assert result["status"] == "SUBMITTED"

    def test_file_dispute_uses_caseNumber_fallback(self):
        """Should also work if response uses 'caseNumber' key."""
        client = _make_client_with_token()
        mock_resp = _make_mock_response({"caseNumber": "EX-ALT-001", "status": "OK"})

        with patch.object(client._session, "request", return_value=mock_resp):
            result = client.file_dispute(
                "client-002", MINIMAL_CONSUMER, "TL-1", "WRONG_DATES"
            )

        assert result["case_number"] == "EX-ALT-001"

    def test_file_dispute_no_case_number_raises(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response({"status": "OK"})

        with patch.object(client._session, "request", return_value=mock_resp):
            with pytest.raises(DisputeError, match="missing case number"):
                client.file_dispute(
                    "client-002", MINIMAL_CONSUMER, "TL-1", "REASON"
                )

    def test_file_dispute_api_error(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response({}, status_code=400)

        with patch.object(client._session, "request", return_value=mock_resp):
            with pytest.raises(DisputeError):
                client.file_dispute("client-002", MINIMAL_CONSUMER, "TL-1", "REASON")

    def test_file_dispute_with_statement(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response(MOCK_DISPUTE_RESPONSE)
        payloads = []

        def capture(method, url, **kwargs):
            payloads.append(kwargs.get("json", {}))
            return mock_resp

        with patch.object(client._session, "request", side_effect=capture):
            client.file_dispute(
                "client-002", MINIMAL_CONSUMER, "TL-1", "WRONG",
                statement="I have never had an account with this creditor."
            )

        stmt = (
            payloads[0]
            .get("disputeInput", {})
            .get("disputedItems", [{}])[0]
            .get("consumerStatement", "")
        )
        assert stmt == "I have never had an account with this creditor."


# ---------------------------------------------------------------------------
# Dispute status
# ---------------------------------------------------------------------------

class TestGetDisputeStatus:

    def test_get_status_success(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response(MOCK_STATUS_RESPONSE)

        with patch.object(client._session, "request", return_value=mock_resp):
            result = client.get_dispute_status("client-002", "EX-2026-007890", "987654321")

        assert result["status"] == "UNDER_REVIEW"
        assert result["bureau"] == "experian"
        assert result["case_number"] == "EX-2026-007890"

    def test_get_status_missing_status_field(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response({"lastUpdatedDate": "2026-04-01"})

        with patch.object(client._session, "request", return_value=mock_resp):
            with pytest.raises(ValidationError, match="status"):
                client.get_dispute_status("client-002", "EX-123", "987654321")


# ---------------------------------------------------------------------------
# Monitor changes
# ---------------------------------------------------------------------------

class TestMonitorChanges:

    def test_monitor_changes_returns_alerts(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response(MOCK_CHANGES_RESPONSE)

        with patch.object(client._session, "request", return_value=mock_resp):
            result = client.monitor_changes("client-002", "987654321")

        assert result["change_count"] == 1
        assert result["changes"][0]["type"] == "score_change"

    def test_monitor_changes_empty_response(self):
        client = _make_client_with_token()
        mock_resp = _make_mock_response({"alerts": []})

        with patch.object(client._session, "request", return_value=mock_resp):
            result = client.monitor_changes("client-002", "987654321")

        assert result["change_count"] == 0


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealthCheck:

    def test_health_check_true(self):
        client = _make_client_with_token()
        mock_resp = MagicMock(status_code=200)

        with patch.object(client._session, "get", return_value=mock_resp):
            assert client.health_check() is True

    def test_health_check_false_on_error(self):
        client = _make_client_with_token()
        with patch.object(
            client._session, "get",
            side_effect=requests.exceptions.ConnectionError()
        ):
            assert client.health_check() is False


# ---------------------------------------------------------------------------
# from_env
# ---------------------------------------------------------------------------

class TestFromEnv:

    def test_from_env_production(self, monkeypatch):
        monkeypatch.setenv("EXPERIAN_CLIENT_ID", "prod-id")
        monkeypatch.setenv("EXPERIAN_CLIENT_SECRET", "prod-secret")
        monkeypatch.delenv("EXPERIAN_SANDBOX", raising=False)

        client = ExperianClient.from_env()
        assert client._client_id == "prod-id"
        assert client.sandbox is False

    def test_from_env_sandbox(self, monkeypatch):
        monkeypatch.setenv("EXPERIAN_CLIENT_ID", "sandbox-id")
        monkeypatch.setenv("EXPERIAN_CLIENT_SECRET", "sandbox-secret")
        monkeypatch.setenv("EXPERIAN_SANDBOX", "true")

        client = ExperianClient.from_env()
        assert client.sandbox is True
        assert "sandbox" in client.base_url
