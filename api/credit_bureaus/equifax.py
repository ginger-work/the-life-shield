"""
Equifax API Client — The Life Shield

Authentication:  OAuth 2.0 (client_credentials grant)
API type:        REST / JSON
Compliance:      FCRA

Environment variables:
    EQUIFAX_CLIENT_ID       OAuth client ID
    EQUIFAX_CLIENT_SECRET   OAuth client secret
    EQUIFAX_ORG_ID          Equifax-assigned organisation ID
    EQUIFAX_BASE_URL        (optional) override base URL
    EQUIFAX_TOKEN_URL       (optional) override token URL
    EQUIFAX_SANDBOX         set to "true" for sandbox

Usage::

    from api.credit_bureaus.equifax import EquifaxClient

    client = EquifaxClient.from_env()
    report = client.pull_credit_report("ls-client-001", consumer={...})
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import requests

from .base import (
    AuthenticationError,
    BaseBureauClient,
    CreditBureauError,
    DisputeError,
    ReportPullError,
    ValidationError,
)

logger = logging.getLogger(__name__)

_PROD_BASE_URL = "https://api.equifax.com/business/credit-reports/v1"
_SANDBOX_BASE_URL = "https://api.sandbox.equifax.com/business/credit-reports/v1"
_PROD_TOKEN_URL = "https://api.equifax.com/v2/oauth/token"
_SANDBOX_TOKEN_URL = "https://api.sandbox.equifax.com/v2/oauth/token"


class EquifaxClient(BaseBureauClient):
    """
    Production-ready Equifax API client.

    Supports:
    - OAuth 2.0 token management (auto-refresh)
    - Pull consumer credit reports
    - File FCRA disputes
    - Monitor dispute investigation status
    - Poll credit file change monitoring
    """

    BUREAU_NAME = "equifax"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._client_id: str = config["client_id"]
        self._client_secret: str = config["client_secret"]
        self._org_id: str = config["org_id"]
        self._token_url: str = config.get("token_url", _PROD_TOKEN_URL)

    @classmethod
    def from_env(cls) -> "EquifaxClient":
        """Construct client from environment variables."""
        sandbox = os.getenv("EQUIFAX_SANDBOX", "false").lower() == "true"
        return cls({
            "client_id": os.environ["EQUIFAX_CLIENT_ID"],
            "client_secret": os.environ["EQUIFAX_CLIENT_SECRET"],
            "org_id": os.environ["EQUIFAX_ORG_ID"],
            "base_url": os.getenv(
                "EQUIFAX_BASE_URL",
                _SANDBOX_BASE_URL if sandbox else _PROD_BASE_URL,
            ),
            "token_url": os.getenv(
                "EQUIFAX_TOKEN_URL",
                _SANDBOX_TOKEN_URL if sandbox else _PROD_TOKEN_URL,
            ),
            "sandbox": sandbox,
            "timeout": int(os.getenv("EQUIFAX_TIMEOUT", "30")),
            "max_retries": int(os.getenv("EQUIFAX_MAX_RETRIES", "3")),
        })

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _authenticate(self) -> str:
        """Obtain OAuth 2.0 access token via client_credentials grant."""
        logger.debug("Equifax: requesting new OAuth token")
        try:
            resp = requests.post(
                self._token_url,
                data={
                    "grant_type": "client_credentials",
                    "scope": "https://api.equifax.com/credit-reports",
                },
                auth=(self._client_id, self._client_secret),
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise AuthenticationError(
                f"Equifax token request network error: {exc}"
            ) from exc

        if resp.status_code != 200:
            raise AuthenticationError(
                f"Equifax token request failed [{resp.status_code}]: {resp.text}"
            )

        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise AuthenticationError("Equifax token response missing access_token")

        expires_in = int(data.get("expires_in", 3600))
        self._token_expiry = time.time() + expires_in
        logger.debug("Equifax: token acquired, expires_in=%ds", expires_in)
        return token

    # ------------------------------------------------------------------
    # Pull credit report
    # ------------------------------------------------------------------

    def pull_credit_report(
        self, client_id: str, consumer: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Pull a full Equifax consumer credit report.

        Args:
            client_id: Internal Life Shield client identifier.
            consumer:  Dict with keys: ssn, dob, first_name, last_name, address.
                       address is dict with: line1, city, state, zip.

        Returns:
            Normalised dict with keys: bureau, client_id, report_date, score,
            tradelines, inquiries, public_records, disputes, collections, raw.
        """
        self._validate_consumer(consumer)

        payload = {
            "consumers": {
                "name": [{
                    "identifier": "current",
                    "firstName": consumer["first_name"],
                    "lastName": consumer["last_name"],
                }],
                "socialNum": [{
                    "identifier": "current",
                    "number": consumer["ssn"].replace("-", ""),
                }],
                "birthDate": consumer["dob"],
                "addresses": [{
                    "identifier": "current",
                    "street": consumer["address"]["line1"],
                    "city": consumer["address"]["city"],
                    "state": consumer["address"]["state"],
                    "zip": consumer["address"]["zip"],
                }],
            },
            "permissiblePurpose": {
                "type": "06",
                "terms": "consumer initiated",
            },
        }

        try:
            raw = self._request(
                "POST", "/consumer-credit-report",
                client_id=client_id, operation="pull_credit_report",
                json=payload,
            )
        except CreditBureauError as exc:
            raise ReportPullError(f"Equifax report pull failed: {exc}") from exc

        return self._normalise_report(raw, client_id)

    def _normalise_report(self, raw: Dict[str, Any], client_id: str) -> Dict[str, Any]:
        """Transform raw Equifax response into Life Shield standard schema."""
        report = raw.get("consumerCreditReport", [{}])
        report_data = report[0] if isinstance(report, list) and report else report

        score_models = report_data.get("scoreCard", [{}])
        score_val = None
        if score_models:
            score_val = score_models[0].get("score", {}).get("results")

        return {
            "bureau": "equifax",
            "client_id": client_id,
            "report_date": datetime.now(timezone.utc).isoformat(),
            "score": score_val,
            "tradelines": report_data.get("tradelines", []),
            "inquiries": report_data.get("inquiries", []),
            "public_records": report_data.get("bankruptcies", []),
            "disputes": report_data.get("disputes", []),
            "collections": report_data.get("collections", []),
            "raw": raw,
        }

    # ------------------------------------------------------------------
    # File dispute
    # ------------------------------------------------------------------

    def file_dispute(
        self,
        client_id: str,
        consumer: Dict[str, Any],
        item_id: str,
        reason: str,
        statement: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        File an FCRA dispute with Equifax.

        Args:
            client_id:  Life Shield client ID.
            consumer:   Dict with at least ssn, dob, first_name, last_name.
            item_id:    The tradeline / inquiry / record ID to dispute.
            reason:     Dispute reason code or free-text description.
            statement:  Optional consumer statement (up to 100 words per FCRA).

        Returns:
            Dict with: case_number, filed_at, expected_resolution_date, status.
        """
        self._validate_consumer(consumer, require_address=False)

        payload = {
            "consumerId": {
                "ssn": consumer["ssn"].replace("-", ""),
                "firstName": consumer["first_name"],
                "lastName": consumer["last_name"],
            },
            "disputedItems": [{
                "itemId": item_id,
                "reason": reason,
                "consumerStatement": statement or "",
            }],
            "permissiblePurpose": {"type": "dispute"},
        }

        try:
            raw = self._request(
                "POST", "/disputes",
                client_id=client_id, operation="file_dispute",
                json=payload,
            )
        except CreditBureauError as exc:
            raise DisputeError(f"Equifax dispute submission failed: {exc}") from exc

        self._require_fields(raw, "caseNumber")
        filed_at = datetime.now(timezone.utc)

        return {
            "bureau": "equifax",
            "client_id": client_id,
            "case_number": raw["caseNumber"],
            "item_id": item_id,
            "reason": reason,
            "status": raw.get("status", "FILED"),
            "filed_at": filed_at.isoformat(),
            "expected_resolution_date": (filed_at + timedelta(days=30)).isoformat(),
            "raw": raw,
        }

    # ------------------------------------------------------------------
    # Dispute status
    # ------------------------------------------------------------------

    def get_dispute_status(
        self, client_id: str, case_number: str, ssn: str
    ) -> Dict[str, Any]:
        """
        Check status of a previously filed Equifax dispute.

        Returns:
            Dict with: case_number, status, updated_at, resolution, raw.
        """
        raw = self._request(
            "GET", f"/disputes/{case_number}",
            client_id=client_id, operation="get_dispute_status",
            params={"ssn": ssn.replace("-", "")},
        )
        self._require_fields(raw, "caseNumber", "status")

        return {
            "bureau": "equifax",
            "client_id": client_id,
            "case_number": raw["caseNumber"],
            "status": raw["status"],
            "updated_at": raw.get("lastUpdated", datetime.now(timezone.utc).isoformat()),
            "expected_resolution_date": raw.get("expectedResolutionDate"),
            "resolution": raw.get("resolution"),
            "raw": raw,
        }

    # ------------------------------------------------------------------
    # Monitor changes
    # ------------------------------------------------------------------

    def monitor_changes(
        self, client_id: str, ssn: str, monitoring_type: str = "daily"
    ) -> Dict[str, Any]:
        """Poll Equifax for recent changes to a consumer's credit file."""
        raw = self._request(
            "GET", "/monitoring/changes",
            client_id=client_id, operation="monitor_changes",
            params={"ssn": ssn.replace("-", ""), "monitoringType": monitoring_type},
        )
        changes = raw.get("changes", raw.get("creditFileChanges", []))
        return {
            "bureau": "equifax",
            "client_id": client_id,
            "changes": changes,
            "change_count": len(changes),
            "polled_at": datetime.now(timezone.utc).isoformat(),
            "raw": raw,
        }

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """Verify the Equifax API is reachable and auth succeeds."""
        try:
            self._get_token()
            resp = self._session.get(
                f"{self.base_url}/health",
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            logger.warning("Equifax health check failed", exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_consumer(consumer: Dict[str, Any], require_address: bool = True) -> None:
        required = {"ssn", "dob", "first_name", "last_name"}
        if require_address:
            required.add("address")
        missing = required - consumer.keys()
        if missing:
            raise ValidationError(f"Consumer dict missing required fields: {sorted(missing)}")
        if require_address and "address" in consumer:
            addr_required = {"line1", "city", "state", "zip"}
            missing_addr = addr_required - consumer["address"].keys()
            if missing_addr:
                raise ValidationError(f"Consumer address missing fields: {sorted(missing_addr)}")
