"""
Tests for api.credit_bureaus.client_factory — CreditBureauFactory & Bureau

Coverage target: 80%+
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from api.credit_bureaus.client_factory import Bureau, CreditBureauFactory
from api.credit_bureaus.base import BaseBureauClient, CreditBureauError
from api.credit_bureaus.equifax import EquifaxClient
from api.credit_bureaus.experian import ExperianClient
from api.credit_bureaus.transunion import TransUnionClient
from api.credit_bureaus.isoftpull import iSoftPullClient


# ---------------------------------------------------------------------------
# Shared configs for testing
# ---------------------------------------------------------------------------

EQUIFAX_CONFIG = {
    "client_id": "eq-id", "client_secret": "eq-secret", "org_id": "eq-org",
    "base_url": "https://sandbox.equifax.com/v1",
    "token_url": "https://sandbox.equifax.com/token",
    "sandbox": True, "timeout": 5, "max_retries": 1,
}

EXPERIAN_CONFIG = {
    "client_id": "ex-id", "client_secret": "ex-secret",
    "base_url": "https://sandbox.experian.com/v2",
    "token_url": "https://sandbox.experian.com/token",
    "sandbox": True, "timeout": 5, "max_retries": 1,
}

TRANSUNION_CONFIG = {
    "api_key": "tu-key", "api_secret": "tu-secret",
    "base_url": "https://apitest.transunion.com/v1",
    "token_url": "https://apitest.transunion.com/token",
    "sandbox": True, "timeout": 5, "max_retries": 1,
}

ISOFTPULL_CONFIG = {
    "api_key": "isp-key",
    "base_url": "https://sandbox.isoftpull.com/v1",
    "sandbox": True, "timeout": 5, "max_retries": 1,
    "rate_limit_per_minute": 120,
}

ALL_CONFIGS = {
    Bureau.EQUIFAX: EQUIFAX_CONFIG,
    Bureau.EXPERIAN: EXPERIAN_CONFIG,
    Bureau.TRANSUNION: TRANSUNION_CONFIG,
    Bureau.ISOFTPULL: ISOFTPULL_CONFIG,
}

VALID_CONSUMER = {
    "ssn": "123-45-6789", "dob": "1985-03-17",
    "first_name": "John", "last_name": "Smith",
    "address": {"line1": "123 Main St", "city": "Charlotte", "state": "NC", "zip": "28201"},
}


def _make_factory() -> CreditBureauFactory:
    return CreditBureauFactory.from_configs(ALL_CONFIGS)


# ---------------------------------------------------------------------------
# Bureau enum
# ---------------------------------------------------------------------------

class TestBureau:

    def test_from_string_equifax(self):
        assert Bureau.from_string("equifax") == Bureau.EQUIFAX

    def test_from_string_case_insensitive(self):
        assert Bureau.from_string("EQUIFAX") == Bureau.EQUIFAX
        assert Bureau.from_string("Experian") == Bureau.EXPERIAN

    def test_from_string_transunion_no_separator(self):
        assert Bureau.from_string("transunion") == Bureau.TRANSUNION
        assert Bureau.from_string("trans_union") == Bureau.TRANSUNION
        assert Bureau.from_string("trans-union") == Bureau.TRANSUNION

    def test_from_string_isoftpull(self):
        assert Bureau.from_string("isoftpull") == Bureau.ISOFTPULL
        assert Bureau.from_string("softpull") == Bureau.ISOFTPULL

    def test_from_string_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown bureau"):
            Bureau.from_string("unknown_bureau")

    def test_from_string_empty_raises(self):
        with pytest.raises(ValueError):
            Bureau.from_string("")


# ---------------------------------------------------------------------------
# Factory construction
# ---------------------------------------------------------------------------

class TestFactoryConstruction:

    def test_from_configs(self):
        factory = CreditBureauFactory.from_configs(ALL_CONFIGS)
        assert factory._configs == ALL_CONFIGS

    def test_from_env_creates_empty_configs(self):
        factory = CreditBureauFactory.from_env()
        assert factory._configs == {}


# ---------------------------------------------------------------------------
# Client access
# ---------------------------------------------------------------------------

class TestGetClient:

    def test_get_equifax_client(self):
        factory = _make_factory()
        client = factory.get_client(Bureau.EQUIFAX)
        assert isinstance(client, EquifaxClient)
        assert client.BUREAU_NAME == "equifax"

    def test_get_experian_client(self):
        factory = _make_factory()
        client = factory.get_client(Bureau.EXPERIAN)
        assert isinstance(client, ExperianClient)

    def test_get_transunion_client(self):
        factory = _make_factory()
        client = factory.get_client(Bureau.TRANSUNION)
        assert isinstance(client, TransUnionClient)

    def test_get_isoftpull_client(self):
        factory = _make_factory()
        client = factory.get_client(Bureau.ISOFTPULL)
        assert isinstance(client, iSoftPullClient)

    def test_client_singleton(self):
        """Same client instance returned on repeated calls."""
        factory = _make_factory()
        c1 = factory.get_client(Bureau.EQUIFAX)
        c2 = factory.get_client(Bureau.EQUIFAX)
        assert c1 is c2

    def test_get_client_by_name(self):
        factory = _make_factory()
        client = factory.get_client_by_name("experian")
        assert isinstance(client, ExperianClient)

    def test_get_client_by_name_case_insensitive(self):
        factory = _make_factory()
        client = factory.get_client_by_name("TransUnion")
        assert isinstance(client, TransUnionClient)


# ---------------------------------------------------------------------------
# High-level operations
# ---------------------------------------------------------------------------

class TestPullReport:

    def test_pull_report_delegates(self):
        factory = _make_factory()
        mock_report = {"bureau": "equifax", "score": 720}

        with patch.object(EquifaxClient, "pull_credit_report", return_value=mock_report):
            result = factory.pull_report(Bureau.EQUIFAX, "client-001", VALID_CONSUMER)

        assert result["score"] == 720


class TestPullAllReports:

    def test_pull_all_reports_success(self):
        factory = _make_factory()

        eq_report = {"bureau": "equifax", "score": 720}
        ex_report = {"bureau": "experian", "score": 730}
        tu_report = {"bureau": "transunion", "score": 710}

        with patch.object(EquifaxClient, "pull_credit_report", return_value=eq_report), \
             patch.object(ExperianClient, "pull_credit_report", return_value=ex_report), \
             patch.object(TransUnionClient, "pull_credit_report", return_value=tu_report):
            results = factory.pull_all_reports("client-001", VALID_CONSUMER)

        assert results["equifax"]["score"] == 720
        assert results["experian"]["score"] == 730
        assert results["transunion"]["score"] == 710

    def test_pull_all_reports_handles_partial_failure(self):
        factory = _make_factory()

        eq_report = {"bureau": "equifax", "score": 720}

        with patch.object(EquifaxClient, "pull_credit_report", return_value=eq_report), \
             patch.object(ExperianClient, "pull_credit_report", side_effect=CreditBureauError("down")), \
             patch.object(TransUnionClient, "pull_credit_report", return_value={"bureau": "transunion", "score": 700}):
            results = factory.pull_all_reports("client-001", VALID_CONSUMER)

        assert results["equifax"]["score"] == 720
        assert "error" in results["experian"]
        assert results["transunion"]["score"] == 700

    def test_pull_all_reports_custom_bureaus(self):
        factory = _make_factory()

        eq_report = {"bureau": "equifax", "score": 720}

        with patch.object(EquifaxClient, "pull_credit_report", return_value=eq_report):
            results = factory.pull_all_reports(
                "client-001", VALID_CONSUMER,
                bureaus=[Bureau.EQUIFAX],
            )

        assert "equifax" in results
        assert "experian" not in results


class TestFileDispute:

    def test_file_dispute_delegates(self):
        factory = _make_factory()
        mock_dispute = {"bureau": "equifax", "case_number": "EQ-123"}

        with patch.object(EquifaxClient, "file_dispute", return_value=mock_dispute):
            result = factory.file_dispute(
                Bureau.EQUIFAX, "client-001", VALID_CONSUMER, "TL-1", "WRONG",
            )

        assert result["case_number"] == "EQ-123"


class TestFileDisputeAllBureaus:

    def test_file_dispute_all_success(self):
        factory = _make_factory()

        eq_result = {"bureau": "equifax", "case_number": "EQ-1"}
        tu_result = {"bureau": "transunion", "case_number": "TU-1"}

        with patch.object(EquifaxClient, "file_dispute", return_value=eq_result), \
             patch.object(TransUnionClient, "file_dispute", return_value=tu_result):
            results = factory.file_dispute_all_bureaus(
                "client-001", VALID_CONSUMER,
                disputes=[
                    {"bureau": Bureau.EQUIFAX, "item_id": "TL-A", "reason": "WRONG"},
                    {"bureau": "transunion", "item_id": "TL-B", "reason": "NOT_MINE"},
                ],
            )

        assert "equifax:TL-A" in results
        assert "transunion:TL-B" in results


class TestGetDisputeStatus:

    def test_get_dispute_status_delegates(self):
        factory = _make_factory()
        mock_status = {"status": "IN_PROGRESS"}

        with patch.object(ExperianClient, "get_dispute_status", return_value=mock_status):
            result = factory.get_dispute_status(
                Bureau.EXPERIAN, "client-001", "EX-123", "123456789",
            )

        assert result["status"] == "IN_PROGRESS"


class TestMonitorChanges:

    def test_monitor_changes_delegates(self):
        factory = _make_factory()
        mock_changes = {"changes": [{"type": "new_inquiry"}], "change_count": 1}

        with patch.object(TransUnionClient, "monitor_changes", return_value=mock_changes):
            result = factory.monitor_changes(Bureau.TRANSUNION, "client-001", "111223333")

        assert result["change_count"] == 1


class TestHealthCheckAll:

    def test_health_check_all_success(self):
        factory = _make_factory()

        with patch.object(EquifaxClient, "health_check", return_value=True), \
             patch.object(ExperianClient, "health_check", return_value=True), \
             patch.object(TransUnionClient, "health_check", return_value=True), \
             patch.object(iSoftPullClient, "health_check", return_value=True):
            results = factory.health_check_all()

        assert results == {
            "equifax": True,
            "experian": True,
            "transunion": True,
            "isoftpull": True,
        }

    def test_health_check_all_partial_failure(self):
        factory = _make_factory()

        with patch.object(EquifaxClient, "health_check", return_value=True), \
             patch.object(ExperianClient, "health_check", return_value=False), \
             patch.object(TransUnionClient, "health_check", return_value=True), \
             patch.object(iSoftPullClient, "health_check", return_value=False):
            results = factory.health_check_all()

        assert results["equifax"] is True
        assert results["experian"] is False
        assert results["transunion"] is True
        assert results["isoftpull"] is False

    def test_health_check_all_exception_returns_false(self):
        factory = _make_factory()

        with patch.object(EquifaxClient, "health_check", side_effect=Exception("boom")), \
             patch.object(ExperianClient, "health_check", return_value=True), \
             patch.object(TransUnionClient, "health_check", return_value=True), \
             patch.object(iSoftPullClient, "health_check", return_value=True):
            results = factory.health_check_all()

        assert results["equifax"] is False
        assert results["experian"] is True
