"""
iSoftPull Soft Credit Pull Client — The Life Shield

Authentication:  API Key (Bearer token in Authorization header)
Score impact:    NONE (soft inquiry only)

Features:
- Soft credit score pulls (no hard inquiry, no score impact)
- Real-time change monitoring + webhooks
- Weekly automated score snapshots
- Alert configuration for score changes, new accounts, new inquiries

Environment variables:
    ISOFTPULL_API_KEY        API key
    ISOFTPULL_BASE_URL       (optional) override
    ISOFTPULL_WEBHOOK_URL    (optional) webhook URL for alerts
    ISOFTPULL_SANDBOX        "true" for sandbox

Usage::

    from api.credit_bureaus.isoftpull import iSoftPullClient
    client = iSoftPullClient.from_env()
    result = client.get_soft_pull("ls-client-001", consumer={"ssn": "...", "dob": "..."})
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import (
    BaseBureauClient,
    CreditBureauError,
    ValidationError,
)

logger = logging.getLogger(__name__)

_PROD_BASE_URL = "https://api.isoftpull.com/v1"
_SANDBOX_BASE_URL = "https://sandbox.api.isoftpull.com/v1"

ALERT_TYPES = [
    "new_inquiry", "new_account", "negative_item",
    "score_change", "address_change", "balance_change", "derogatory_item",
]


class iSoftPullClient(BaseBureauClient):
    """
    iSoftPull soft credit pull and monitoring client.

    Key features:
    - Zero score impact (soft inquiries only)
    - Real-time webhook alerts
    - Weekly automated monitoring snapshots
    - Score change delta tracking
    """

    BUREAU_NAME = "isoftpull"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._api_key: str = config["api_key"]
        self._webhook_url: str = config.get(
            "webhook_url", "https://thelifeshield.com/webhooks/credit-alert"
        )

    @classmethod
    def from_env(cls) -> "iSoftPullClient":
        """Construct client from environment variables."""
        sandbox = os.getenv("ISOFTPULL_SANDBOX", "false").lower() == "true"
        return cls({
            "api_key": os.environ["ISOFTPULL_API_KEY"],
            "base_url": os.getenv(
                "ISOFTPULL_BASE_URL",
                _SANDBOX_BASE_URL if sandbox else _PROD_BASE_URL,
            ),
            "webhook_url": os.getenv(
                "ISOFTPULL_WEBHOOK_URL",
                "https://thelifeshield.com/webhooks/credit-alert",
            ),
            "sandbox": sandbox,
            "timeout": int(os.getenv("ISOFTPULL_TIMEOUT", "15")),
            "max_retries": int(os.getenv("ISOFTPULL_MAX_RETRIES", "3")),
            "rate_limit_per_minute": 120,
        })

    # ------------------------------------------------------------------
    # Authentication (simple API key)
    # ------------------------------------------------------------------

    def _authenticate(self) -> str:
        """iSoftPull uses a static API key — no token exchange required."""
        return self._api_key

    # ------------------------------------------------------------------
    # Soft pull
    # ------------------------------------------------------------------

    def get_soft_pull(
        self, client_id: str, consumer: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Perform a soft credit pull (no score impact).

        Args:
            client_id: Life Shield client identifier.
            consumer:  Dict with keys: ssn, dob (first_name, last_name optional).

        Returns:
            Dict with: score, score_range, scoring_model, factors,
            bureau, pulled_at, pull_type, score_impact, raw.
        """
        self._validate_soft_pull_consumer(consumer)

        params: Dict[str, Any] = {
            "ssn": consumer["ssn"].replace("-", ""),
            "dob": consumer["dob"],
        }
        if "first_name" in consumer:
            params["firstName"] = consumer["first_name"]
        if "last_name" in consumer:
            params["lastName"] = consumer["last_name"]

        raw = self._request(
            "GET", "/softpull/credit-score",
            client_id=client_id, operation="get_soft_pull",
            params=params,
        )

        return {
            "bureau": raw.get("bureau", "transunion"),
            "client_id": client_id,
            "score": raw.get("score") or raw.get("creditScore"),
            "score_range": raw.get("scoreRange", {"min": 300, "max": 850}),
            "scoring_model": raw.get("scoringModel", "VantageScore 3.0"),
            "factors": raw.get("factors", raw.get("scoreFactors", [])),
            "pulled_at": datetime.now(timezone.utc).isoformat(),
            "pull_type": "soft",
            "score_impact": False,
            "raw": raw,
        }

    # ------------------------------------------------------------------
    # Monitoring setup
    # ------------------------------------------------------------------

    def setup_monitoring(
        self,
        client_id: str,
        consumer: Dict[str, Any],
        frequency: str = "weekly",
        alert_types: Optional[List[str]] = None,
        webhook_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Register a consumer for ongoing soft pull monitoring.

        Args:
            client_id:   Life Shield client ID.
            consumer:    Dict with ssn, dob.
            frequency:   "daily", "weekly" (default), or "monthly".
            alert_types: Alert types to subscribe to (default: all).
            webhook_url: Override webhook URL.

        Returns:
            Dict with: monitoring_id, frequency, alert_types, created_at.
        """
        self._validate_soft_pull_consumer(consumer)

        if alert_types is None:
            alert_types = [
                "new_inquiry", "new_account", "negative_item",
                "score_change", "derogatory_item",
            ]

        payload: Dict[str, Any] = {
            "ssn": consumer["ssn"].replace("-", ""),
            "dob": consumer["dob"],
            "frequency": frequency,
            "alertTypes": alert_types,
            "webhookUrl": webhook_url or self._webhook_url,
            "clientRef": client_id,
            "metadata": {"platform": "thelifeshield", "clientId": client_id},
        }
        if "first_name" in consumer:
            payload["firstName"] = consumer["first_name"]
        if "last_name" in consumer:
            payload["lastName"] = consumer["last_name"]

        raw = self._request(
            "POST", "/monitoring/subscribe",
            client_id=client_id, operation="setup_monitoring",
            json=payload,
        )

        monitoring_id = raw.get("monitoringId") or raw.get("subscriptionId")
        return {
            "client_id": client_id,
            "monitoring_id": monitoring_id,
            "frequency": frequency,
            "alert_types": alert_types,
            "webhook_url": webhook_url or self._webhook_url,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "raw": raw,
        }

    # ------------------------------------------------------------------
    # Get changes
    # ------------------------------------------------------------------

    def get_changes(
        self, client_id: str, ssn: str, since: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Poll for credit file changes since the last check.

        Args:
            client_id: Life Shield client ID.
            ssn:       Consumer SSN.
            since:     ISO 8601 timestamp (defaults to 7 days ago).
        """
        params: Dict[str, Any] = {"ssn": ssn.replace("-", "")}
        if since:
            params["since"] = since

        raw = self._request(
            "GET", "/monitoring/changes",
            client_id=client_id, operation="get_changes",
            params=params,
        )

        changes = raw.get("changes", raw.get("alerts", []))
        return {
            "client_id": client_id,
            "changes": changes,
            "change_count": len(changes),
            "polled_at": datetime.now(timezone.utc).isoformat(),
            "raw": raw,
        }

    # ------------------------------------------------------------------
    # Score history
    # ------------------------------------------------------------------

    def get_score_history(
        self, client_id: str, ssn: str, limit: int = 12
    ) -> Dict[str, Any]:
        """
        Retrieve historical credit score snapshots.

        Returns:
            Dict with: snapshots (list), snapshot_count, trend.
        """
        raw = self._request(
            "GET", "/monitoring/score-history",
            client_id=client_id, operation="get_score_history",
            params={"ssn": ssn.replace("-", ""), "limit": limit},
        )

        snapshots = raw.get("scoreHistory", raw.get("snapshots", []))
        trend = "stable"
        if len(snapshots) >= 2:
            first_score = snapshots[-1].get("score", 0)
            last_score = snapshots[0].get("score", 0)
            delta = last_score - first_score
            if delta > 10:
                trend = "improving"
            elif delta < -10:
                trend = "declining"

        return {
            "client_id": client_id,
            "snapshots": snapshots,
            "snapshot_count": len(snapshots),
            "trend": trend,
            "polled_at": datetime.now(timezone.utc).isoformat(),
            "raw": raw,
        }

    # ------------------------------------------------------------------
    # Cancel monitoring
    # ------------------------------------------------------------------

    def cancel_monitoring(self, client_id: str, monitoring_id: str) -> bool:
        """Cancel an active monitoring subscription."""
        raw = self._request(
            "DELETE", f"/monitoring/subscribe/{monitoring_id}",
            client_id=client_id, operation="cancel_monitoring",
        )
        return raw.get("status", "").upper() in {"CANCELLED", "SUCCESS", "DELETED"}

    # ------------------------------------------------------------------
    # BaseBureauClient abstract stubs
    # ------------------------------------------------------------------

    def pull_credit_report(self, client_id: str, consumer: Dict[str, Any]) -> Dict[str, Any]:
        """Alias for get_soft_pull — iSoftPull does not produce full reports."""
        return self.get_soft_pull(client_id, consumer)

    def file_dispute(
        self, client_id: str, consumer: Dict[str, Any],
        item_id: str, reason: str, statement: Optional[str] = None,
    ) -> Dict[str, Any]:
        """iSoftPull does not support dispute filing."""
        raise NotImplementedError(
            "iSoftPull does not support dispute filing. "
            "Use EquifaxClient, ExperianClient, or TransUnionClient."
        )

    def get_dispute_status(
        self, client_id: str, case_number: str, ssn: str
    ) -> Dict[str, Any]:
        """iSoftPull does not track disputes."""
        raise NotImplementedError(
            "iSoftPull does not support dispute status. "
            "Use EquifaxClient, ExperianClient, or TransUnionClient."
        )

    def monitor_changes(
        self, client_id: str, ssn: str, monitoring_type: str = "daily"
    ) -> Dict[str, Any]:
        """Delegate to get_changes()."""
        return self.get_changes(client_id, ssn)

    def health_check(self) -> bool:
        """Return True if iSoftPull API is reachable."""
        try:
            resp = self._session.get(
                f"{self.base_url}/health",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            logger.warning("iSoftPull health check failed", exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_soft_pull_consumer(consumer: Dict[str, Any]) -> None:
        """Validate minimum consumer fields for a soft pull."""
        required = {"ssn", "dob"}
        missing = required - consumer.keys()
        if missing:
            raise ValidationError(
                f"iSoftPull consumer dict missing required fields: {sorted(missing)}"
            )
