"""
Experian API Client — The Life Shield

Authentication:  OAuth 2.0 (client_credentials grant)
API type:        REST / JSON
Compliance:      FCRA

Environment variables:
    EXPERIAN_CLIENT_ID       OAuth client ID
    EXPERIAN_CLIENT_SECRET   OAuth client secret
    EXPERIAN_BASE_URL        (optional) override
    EXPERIAN_TOKEN_URL       (optional) override
    EXPERIAN_SANDBOX         "true" for sandbox

Usage::

    from api.credit_bureaus.experian import ExperianClient
    client = ExperianClient.from_env()
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

_PROD_BASE_URL = "https://us-api.experian.com/consumerservices/credit-profile/v2"
_SANDBOX_BASE_URL = "https://sandbox.experian.com/consumerservices/credit-profile/v2"
_PROD_TOKEN_URL = "https://us-api.experian.com/oauth2/v1/token"
_SANDBOX_TOKEN_URL = "https://sandbox.experian.com/oauth2/v1/token"


class ExperianClient(BaseBureauClient):
    """
    Production-ready Experian API client.

    Supports:
    - OAuth 2.0 token management (auto-refresh)
    - Pull consumer credit reports (VantageScore + tradelines)
    - File FCRA disputes via Experian e-OSCAR portal API
    - Monitor dispute investigation status
    - Poll credit file change monitoring
    """

    BUREAU_NAME = "experian"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._client_id: str = config["client_id"]
        self._client_secret: str = config["client_secret"]
        self._token_url: str = config.get("token_url", _PROD_TOKEN_URL)

    @classmethod
    def from_env(cls) -> "ExperianClient":
        """Construct client from environment variables."""
        sandbox = os.getenv("EXPERIAN_SANDBOX", "false").lower() == "true"
        return cls({
            "client_id": os.environ["EXPERIAN_CLIENT_ID"],
            "client_secret": os.environ["EXPERIAN_CLIENT_SECRET"],
            "base_url": os.getenv(
                "EXPERIAN_BASE_URL",
                _SANDBOX_BASE_URL if sandbox else _PROD_BASE_URL,
            ),
            "token_url": os.getenv(
                "EXPERIAN_TOKEN_URL",
                _SANDBOX_TOKEN_URL if sandbox else _PROD_TOKEN_URL,
            ),
            "sandbox": sandbox,
            "timeout": int(os.getenv("EXPERIAN_TIMEOUT", "30")),
            "max_retries": int(os.getenv("EXPERIAN_MAX_RETRIES", "3")),
        })

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _authenticate(self) -> str:
        """Obtain OAuth 2.0 access token via client_credentials grant."""
        logger.debug("Experian: requesting new OAuth token")
        try:
            resp = requests.post(
                self._token_url,
                data={"grant_type": "client_credentials"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                auth=(self._client_id, self._client_secret),
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise AuthenticationError(
                f"Experian token request network error: {exc}"
            ) from exc

        if resp.status_code != 200:
            raise AuthenticationError(
                f"Experian token request failed [{resp.status_code}]: {resp.text}"
            )

        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise AuthenticationError("Experian token response missing access_token")

        expires_in = int(data.get("expires_in", 1800))
        self._token_expiry = time.time() + expires_in
        logger.debug("Experian: token acquired, expires_in=%ds", expires_in)
        return token

    # ------------------------------------------------------------------
    # Pull credit report
    # ------------------------------------------------------------------

    def pull_credit_report(
        self, client_id: str, consumer: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Pull a full Experian consumer credit report.

        Args:
            client_id: Life Shield client identifier.
            consumer:  Dict with keys: ssn, dob, first_name, last_name,
                       address ({line1, city, state, zip}).

        Returns:
            Normalised report dict.
        """
        self._validate_consumer(consumer)

        payload = {
            "consumerPii": {
                "primaryApplicant": {
                    "name": {
                        "firstName": consumer["first_name"],
                        "lastName": consumer["last_name"],
                    },
                    "ssn": {"full": consumer["ssn"].replace("-", "")},
                    "dob": {"dob": consumer["dob"]},
                    "currentAddress": {
                        "line1": consumer["address"]["line1"],
                        "city": consumer["address"]["city"],
                        "state": consumer["address"]["state"],
                        "zipCode": consumer["address"]["zip"],
                    },
                }
            },
            "requestedAttributes": [
                "CreditProfile", "RiskModels", "TradeLinesSummary",
                "PublicRecordsSummary", "InquiriesSummary", "CollectionsSummary",
            ],
            "permissiblePurpose": {
                "purpose": "0Z",
                "abbreviatedPurpose": "REVIEW",
            },
        }

        try:
            raw = self._request(
                "POST", "/credit-report",
                client_id=client_id, operation="pull_credit_report",
                json=payload,
            )
        except CreditBureauError as exc:
            raise ReportPullError(f"Experian report pull failed: {exc}") from exc

        return self._normalise_report(raw, client_id)

    def _normalise_report(self, raw: Dict[str, Any], client_id: str) -> Dict[str, Any]:
        credit_profile = raw.get("creditProfile", [{}])
        profile = credit_profile[0] if isinstance(credit_profile, list) and credit_profile else credit_profile

        risk_models = profile.get("riskModel", [{}])
        score_val = risk_models[0].get("score") if risk_models else None

        return {
            "bureau": "experian",
            "client_id": client_id,
            "report_date": datetime.now(timezone.utc).isoformat(),
            "score": score_val,
            "tradelines": profile.get("tradeline", []),
            "inquiries": profile.get("inquiry", []),
            "public_records": profile.get("publicRecord", []),
            "disputes": profile.get("dispute", []),
            "collections": profile.get("collection", []),
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
        """File an FCRA dispute with Experian (e-OSCAR API)."""
        self._validate_consumer(consumer, require_address=False)

        payload = {
            "disputeInput": {
                "consumerIdentity": {
                    "name": {
                        "firstName": consumer["first_name"],
                        "lastName": consumer["last_name"],
                    },
                    "ssn": consumer["ssn"].replace("-", ""),
                    "dob": consumer.get("dob", ""),
                },
                "disputedItems": [{
                    "referenceNumber": item_id,
                    "disputeCode": reason,
                    "consumerStatement": statement or "",
                }],
            }
        }

        try:
            raw = self._request(
                "POST", "/disputes",
                client_id=client_id, operation="file_dispute",
                json=payload,
            )
        except CreditBureauError as exc:
            raise DisputeError(f"Experian dispute submission failed: {exc}") from exc

        case_number = (
            raw.get("disputeCaseNumber")
            or raw.get("caseNumber")
            or raw.get("confirmationNumber")
        )
        if not case_number:
            raise DisputeError("Experian dispute response missing case number")

        filed_at = datetime.now(timezone.utc)
        return {
            "bureau": "experian",
            "client_id": client_id,
            "case_number": case_number,
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
        """Check status of a previously filed Experian dispute."""
        raw = self._request(
            "GET", f"/disputes/{case_number}",
            client_id=client_id, operation="get_dispute_status",
            params={"ssn": ssn.replace("-", "")},
        )
        self._require_fields(raw, "status")

        return {
            "bureau": "experian",
            "client_id": client_id,
            "case_number": case_number,
            "status": raw["status"],
            "updated_at": raw.get("lastUpdatedDate", datetime.now(timezone.utc).isoformat()),
            "expected_resolution_date": raw.get("expectedCompletionDate"),
            "resolution": raw.get("outcome"),
            "raw": raw,
        }

    # ------------------------------------------------------------------
    # Monitor changes
    # ------------------------------------------------------------------

    def monitor_changes(
        self, client_id: str, ssn: str, monitoring_type: str = "daily"
    ) -> Dict[str, Any]:
        """Poll Experian for changes to a consumer's credit file."""
        raw = self._request(
            "GET", "/monitoring/alerts",
            client_id=client_id, operation="monitor_changes",
            params={"ssn": ssn.replace("-", ""), "frequency": monitoring_type},
        )
        changes = raw.get("alerts", raw.get("changes", []))
        return {
            "bureau": "experian",
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
        """Return True if the Experian API is reachable."""
        try:
            self._get_token()
            resp = self._session.get(
                f"{self.base_url}/health",
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            logger.warning("Experian health check failed", exc_info=True)
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
