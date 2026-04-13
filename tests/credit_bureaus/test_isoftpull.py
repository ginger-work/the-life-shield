"""
Tests for api.credit_bureaus.isoftpull — iSoftPullClient

Coverage target: 80%+
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from api.credit_bureaus.isoftpull import iSoftPullClient
from api.credit_bureaus.base import CreditBureauError, ValidationError


CONSUMER = {
    "ssn": "555-66-7777",
    "dob": "1992-08-15",
    "first_name": "Sarah",
    "last_name": "Chen",
}

MINIMAL_CONSUMER = {"ssn": "555-66-7777", "dob": "1992-08-15"}

CLIENT_CONFIG = {
    "api_key": "isp-test-key-12345",
    "base_url": "https://sandbox.api.isoftpull.com/v1",
    "webhook_url": "https://thelifeshield.com/webhooks/credit-alert",
    "sandbox": True,
    "timeout": 10,
    "max_retries": 1,
    "rate_limit_per_minute": 120,
}

MOCK_SOFT_PULL_RESPONSE = {
    "score": 712,
    "bureau": "transunion",
    "scoreRange": {"min": 300, "max": 850},
    "scoringModel": "VantageScore 3.0",
    "factors": ["HIGH_UTIL", "SHORT_HISTORY"],
}

MOCK_MONITORING_RESPONSE = {
    "monitoringId": "mon-abc-123",
    "status": "ACTIVE",
}

MOCK_CHANGES_RESPONSE = {
    "changes": [
        {"type": "score_change", "previous": 700, "current": 712, "date": "2026-04-10"},
        {"type": "new_inquiry", "creditor": "Amex", "date": "2026-04-08"},
    ]
}

MOCK_SCORE_HISTORY = {
    "scoreHistory": [
        {"score": 712, "date": "2026-04-01"},
        {"score": 700, "date": "2026-03-01"},
        {"score": 688, "date": "2026-02-01"},
        {"score": 675, "date": "2026-01-01"},
    ]
}

MOCK_CANCEL_RESPONSE = {"status": "CANCELLED"}


def _mock_resp(json_data: dict, status_code: int = 200) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.text = str(json_data)
    return mock


def _authed_client() -> iSoftPullClient:
    client = iSoftPullClient(CLIENT_CONFIG)
    # API key auth — token is always the key
    client._token = "isp-test-key-12345"
    client._token_expiry = time.time() + 999999
    return client


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class TestAuthentication:

    def test_authenticate_returns_api_key(self):
        client = iSoftPullClient(CLIENT_CONFIG)
        assert client._authenticate() == "isp-test-key-12345"


# ---------------------------------------------------------------------------
# Soft pull
# ---------------------------------------------------------------------------

class TestGetSoftPull:

    def test_soft_pull_success(self):
        client = _authed_client()
        mock = _mock_resp(MOCK_SOFT_PULL_RESPONSE)

        with patch.object(client._session, "request", return_value=mock):
            result = client.get_soft_pull("client-004", CONSUMER)

        assert result["score"] == 712
        assert result["bureau"] == "transunion"
        assert result["pull_type"] == "soft"
        assert result["score_impact"] is False
        assert result["scoring_model"] == "VantageScore 3.0"
        assert len(result["factors"]) == 2
        assert "pulled_at" in result

    def test_soft_pull_minimal_consumer(self):
        """Only ssn and dob are required."""
        client = _authed_client()
        mock = _mock_resp(MOCK_SOFT_PULL_RESPONSE)

        with patch.object(client._session, "request", return_value=mock):
            result = client.get_soft_pull("client-004", MINIMAL_CONSUMER)

        assert result["score"] == 712

    def test_soft_pull_missing_ssn(self):
        client = _authed_client()

        with pytest.raises(ValidationError, match="ssn"):
            client.get_soft_pull("client-004", {"dob": "1992-08-15"})

    def test_soft_pull_missing_dob(self):
        client = _authed_client()

        with pytest.raises(ValidationError, match="dob"):
            client.get_soft_pull("client-004", {"ssn": "555667777"})

    def test_soft_pull_uses_creditScore_fallback(self):
        client = _authed_client()
        mock = _mock_resp({"creditScore": 650})

        with patch.object(client._session, "request", return_value=mock):
            result = client.get_soft_pull("client-004", MINIMAL_CONSUMER)

        assert result["score"] == 650

    def test_soft_pull_api_error(self):
        client = _authed_client()
        mock = _mock_resp({}, status_code=500)

        with patch.object(client._session, "request", return_value=mock):
            with pytest.raises(CreditBureauError):
                client.get_soft_pull("client-004", MINIMAL_CONSUMER)

    def test_soft_pull_timeout(self):
        client = _authed_client()

        with patch.object(
            client._session, "request",
            side_effect=requests.exceptions.Timeout()
        ):
            with pytest.raises(CreditBureauError, match="timed out"):
                client.get_soft_pull("client-004", MINIMAL_CONSUMER)

    def test_soft_pull_ssn_sanitised(self):
        client = _authed_client()
        mock = _mock_resp(MOCK_SOFT_PULL_RESPONSE)
        captured = []

        def capture(method, url, **kwargs):
            captured.append(kwargs.get("params", {}))
            return mock

        with patch.object(client._session, "request", side_effect=capture):
            client.get_soft_pull("client-004", CONSUMER)

        assert "-" not in captured[0].get("ssn", "")

    def test_pull_credit_report_delegates_to_soft_pull(self):
        """pull_credit_report() should alias to get_soft_pull()."""
        client = _authed_client()
        mock = _mock_resp(MOCK_SOFT_PULL_RESPONSE)

        with patch.object(client._session, "request", return_value=mock):
            result = client.pull_credit_report("client-004", CONSUMER)

        assert result["pull_type"] == "soft"


# ---------------------------------------------------------------------------
# Monitoring setup
# ---------------------------------------------------------------------------

class TestSetupMonitoring:

    def test_setup_monitoring_success(self):
        client = _authed_client()
        mock = _mock_resp(MOCK_MONITORING_RESPONSE)

        with patch.object(client._session, "request", return_value=mock):
            result = client.setup_monitoring("client-004", MINIMAL_CONSUMER)

        assert result["monitoring_id"] == "mon-abc-123"
        assert result["frequency"] == "weekly"
        assert "new_inquiry" in result["alert_types"]
        assert "created_at" in result

    def test_setup_monitoring_custom_frequency(self):
        client = _authed_client()
        mock = _mock_resp(MOCK_MONITORING_RESPONSE)
        captured = []

        def capture(method, url, **kwargs):
            captured.append(kwargs.get("json", {}))
            return mock

        with patch.object(client._session, "request", side_effect=capture):
            client.setup_monitoring(
                "client-004", MINIMAL_CONSUMER, frequency="daily"
            )

        assert captured[0]["frequency"] == "daily"

    def test_setup_monitoring_custom_alert_types(self):
        client = _authed_client()
        mock = _mock_resp(MOCK_MONITORING_RESPONSE)

        with patch.object(client._session, "request", return_value=mock):
            result = client.setup_monitoring(
                "client-004", MINIMAL_CONSUMER,
                alert_types=["score_change"],
            )

        assert result["alert_types"] == ["score_change"]

    def test_setup_monitoring_custom_webhook(self):
        client = _authed_client()
        mock = _mock_resp(MOCK_MONITORING_RESPONSE)
        captured = []

        def capture(method, url, **kwargs):
            captured.append(kwargs.get("json", {}))
            return mock

        with patch.object(client._session, "request", side_effect=capture):
            client.setup_monitoring(
                "client-004", MINIMAL_CONSUMER,
                webhook_url="https://custom.example.com/hook",
            )

        assert captured[0]["webhookUrl"] == "https://custom.example.com/hook"


# ---------------------------------------------------------------------------
# Get changes
# ---------------------------------------------------------------------------

class TestGetChanges:

    def test_get_changes_success(self):
        client = _authed_client()
        mock = _mock_resp(MOCK_CHANGES_RESPONSE)

        with patch.object(client._session, "request", return_value=mock):
            result = client.get_changes("client-004", "555667777")

        assert result["change_count"] == 2
        assert result["changes"][0]["type"] == "score_change"

    def test_get_changes_with_since_param(self):
        client = _authed_client()
        mock = _mock_resp({"changes": []})
        captured = []

        def capture(method, url, **kwargs):
            captured.append(kwargs.get("params", {}))
            return mock

        with patch.object(client._session, "request", side_effect=capture):
            client.get_changes("client-004", "555667777", since="2026-04-01T00:00:00Z")

        assert captured[0]["since"] == "2026-04-01T00:00:00Z"

    def test_get_changes_empty(self):
        client = _authed_client()
        mock = _mock_resp({"changes": []})

        with patch.object(client._session, "request", return_value=mock):
            result = client.get_changes("client-004", "555667777")

        assert result["change_count"] == 0

    def test_monitor_changes_delegates_to_get_changes(self):
        client = _authed_client()
        mock = _mock_resp(MOCK_CHANGES_RESPONSE)

        with patch.object(client._session, "request", return_value=mock):
            result = client.monitor_changes("client-004", "555667777")

        assert result["change_count"] == 2


# ---------------------------------------------------------------------------
# Score history
# ---------------------------------------------------------------------------

class TestScoreHistory:

    def test_get_score_history_improving(self):
        client = _authed_client()
        mock = _mock_resp(MOCK_SCORE_HISTORY)

        with patch.object(client._session, "request", return_value=mock):
            result = client.get_score_history("client-004", "555667777")

        assert result["snapshot_count"] == 4
        assert result["trend"] == "improving"
        assert result["snapshots"][0]["score"] == 712

    def test_get_score_history_declining(self):
        client = _authed_client()
        declining = {
            "scoreHistory": [
                {"score": 620, "date": "2026-04-01"},
                {"score": 680, "date": "2026-01-01"},
            ]
        }
        mock = _mock_resp(declining)

        with patch.object(client._session, "request", return_value=mock):
            result = client.get_score_history("client-004", "555667777")

        assert result["trend"] == "declining"

    def test_get_score_history_stable(self):
        client = _authed_client()
        stable = {
            "scoreHistory": [
                {"score": 700, "date": "2026-04-01"},
                {"score": 695, "date": "2026-01-01"},
            ]
        }
        mock = _mock_resp(stable)

        with patch.object(client._session, "request", return_value=mock):
            result = client.get_score_history("client-004", "555667777")

        assert result["trend"] == "stable"

    def test_get_score_history_single_snapshot(self):
        client = _authed_client()
        mock = _mock_resp({"scoreHistory": [{"score": 700, "date": "2026-04-01"}]})

        with patch.object(client._session, "request", return_value=mock):
            result = client.get_score_history("client-004", "555667777")

        assert result["trend"] == "stable"
        assert result["snapshot_count"] == 1


# ---------------------------------------------------------------------------
# Cancel monitoring
# ---------------------------------------------------------------------------

class TestCancelMonitoring:

    def test_cancel_success(self):
        client = _authed_client()
        mock = _mock_resp(MOCK_CANCEL_RESPONSE)

        with patch.object(client._session, "request", return_value=mock):
            assert client.cancel_monitoring("client-004", "mon-abc-123") is True

    def test_cancel_returns_false_on_unknown_status(self):
        client = _authed_client()
        mock = _mock_resp({"status": "PENDING"})

        with patch.object(client._session, "request", return_value=mock):
            assert client.cancel_monitoring("client-004", "mon-abc-123") is False


# ---------------------------------------------------------------------------
# Dispute stubs (not supported)
# ---------------------------------------------------------------------------

class TestDisputeStubs:

    def test_file_dispute_raises_not_implemented(self):
        client = _authed_client()

        with pytest.raises(NotImplementedError, match="does not support dispute filing"):
            client.file_dispute("client-004", CONSUMER, "TL-1", "REASON")

    def test_get_dispute_status_raises_not_implemented(self):
        client = _authed_client()

        with pytest.raises(NotImplementedError, match="does not support dispute status"):
            client.get_dispute_status("client-004", "CASE-1", "555667777")


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
        monkeypatch.setenv("ISOFTPULL_API_KEY", "env-isp-key")
        monkeypatch.setenv("ISOFTPULL_SANDBOX", "true")

        client = iSoftPullClient.from_env()
        assert client._api_key == "env-isp-key"
        assert client.sandbox is True

    def test_from_env_missing_key(self, monkeypatch):
        monkeypatch.delenv("ISOFTPULL_API_KEY", raising=False)

        with pytest.raises(KeyError):
            iSoftPullClient.from_env()
