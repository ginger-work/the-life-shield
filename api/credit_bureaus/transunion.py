"""
TransUnion API Client — The Life Shield

Authentication:  HMAC-signed API Key + Secret → Bearer token exchange
API type:        REST / JSON
Compliance:      FCRA

Environment variables:
    TRANSUNION_API_KEY       API key from TransUnion
    TRANSUNION_API_SECRET    API secret (HMAC signing)
    TRANSUNION_BASE_URL      (optional) override
    TRANSUNION_TOKEN_URL     (optional) override
    TRANSUNION_SANDBOX       "true" for sandbox

Usage::

    from api.credit_bureaus.transunion import TransUnionClient
    client = TransUnionClient.from_env()
    report = client.pull_credit_report("ls-client-001", consumer={...})
"""

from __future__ import annotations

import hashlib
import hmac
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

_PROD_BASE_URL = "https://api.transunion.com/credit-reports/v1"
_SANDBOX_BASE_URL = "https://apitest.transunion.com/credit-reports/v1"
_PROD_TOKEN_URL = "https://api.transunion.com/auth/v1/token"
_SANDBOX_TOKEN_URL = "https://apitest.transunion.com/auth/v1/token"


class TransUnionClient(BaseBureauClient):
    """
    Production-ready TransUnion API client.

    Uses HMAC-SHA256 signed credentials exchanged for a short-lived Bearer token.

    Supports:
    - Pull consumer credit reports (VantageScore + tradelines)
    - File FCRA disputes
    - Monitor dispute investigation status
    - Poll credit file change monitoring
    """

    BUREAU_NAME = "transunion"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._api_key: str = config["api_key"]
        self._api_secret: str = config["api_secret"]
        self._token_url: str = config.get("token_url", _PROD_TOKEN_URL)

    @classmethod
    def from_env(cls) -> "TransUnionClient":
        """Construct client from environment variables."""
        sandbox = os.getenv("TRANSUNION_SANDBOX", "false").lower() == "true"
        return cls({
            "api_key": os.environ["TRANSUNION_API_KEY"],
            "api_secret": os.environ["TRANSUNION_API_SECRET"],
            "base_url": os.getenv(
                "TRANSUNION_BASE_URL",
                _SANDBOX_BASE_URL if sandbox else _PROD_BASE_URL,
            ),
            "token_url": os.getenv(
                "TRANSUNION_TOKEN_URL",
                _SANDBOX_TOKEN_URL if sandbox else _PROD_TOKEN_URL,
            ),
            "sandbox": sandbox,
            "timeout": int(os.getenv("TRANSUNION_TIMEOUT", "30")),
            "max_retries": int(os.getenv("TRANSUNION_MAX_RETRIES", "3")),
        })

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _sign_request(self, timestamp: str) -> str:
        """HMAC-SHA256 sign: api_key + ":" + timestamp."""
        message = f"{self._api_key}:{timestamp}"
        return hmac.new(
            self._api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _authenticate(self) -> str:
        """Exchange HMAC-signed credentials for a short-lived Bearer token."""
        logger.debug("TransUnion: exchanging credentials for bearer token")
        timestamp = str(int(time.time()))
        signature = self._sign_request(timestamp)

        try:
            resp = requests.post(
                self._token_url,
                json={
                    "apiKey": self._api_key,
                    "timestamp": timestamp,
                    "signature": signature,
                },
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise AuthenticationError(
                f"TransUnion token request network error: {exc}"
            ) from exc

        if resp.status_code != 200:
            raise AuthenticationError(
                f"TransUnion token request failed [{resp.status_code}]: {resp.text}"
            )

        data = resp.json()
        token = data.get("accessToken") or data.get("access_token")
        if not token:
            raise AuthenticationError("TransUnion token response missing accessToken")

        expires_in = int(data.get("expiresIn", data.get("expires_in", 3600)))
        self._token_expiry = time.time() + expires_in
        logger.debug("TransUnion: token acquired, expires_in=%ds", expires_in)
        return token

    # ------------------------------------------------------------------
    # Pull credit report
    # ------------------------------------------------------------------

    def pull_credit_report(
        self, client_id: str, consumer: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Pull a full TransUnion consumer credit report.

        Args:
            client_id: Life Shield client identifier.
            consumer:  Dict with keys: ssn, dob, first_name, last_name,
                       address ({line1, city, state, zip}).
        """
        self._validate_consumer(consumer)

        payload = {
            "request": {
                "subscribers": [{
                    "industryCode": "Y",
                    "memberCode": self._api_key,
                    "prefix": "TLS",
                    "password": "",
                }],
                "permissiblePurpose": {
                    "inquiryType": "Account Review",
                    "leverageType": "Individual",
                },
                "product": [{
                    "code": "06221",
                    "subject": {
                        "subjectRecord": {
                            "indicative": {
                                "name": [{
                                    "person": {
                                        "first": consumer["first_name"],
                                        "last": consumer["last_name"],
                                    }
                                }],
                                "address": [{
                                    "status": "current",
                                    "street": {"unparsed": consumer["address"]["line1"]},
                                    "location": {
                                        "city": consumer["address"]["city"],
                                        "state": consumer["address"]["state"],
                                        "zipCode": consumer["address"]["zip"],
                                    },
                                }],
                                "socialSecurity": {
                                    "number": consumer["ssn"].replace("-", "")
                                },
                                "dateOfBirth": consumer["dob"],
                            }
                        }
                    },
                }],
            }
        }

        try:
            raw = self._request(
                "POST", "/report",
                client_id=client_id, operation="pull_credit_report",
                json=payload,
            )
        except CreditBureauError as exc:
            raise ReportPullError(f"TransUnion report pull failed: {exc}") from exc

        return self._normalise_report(raw, client_id)

    def _normalise_report(self, raw: Dict[str, Any], client_id: str) -> Dict[str, Any]:
        credit_report = raw.get("creditReport", {})
        product = credit_report.get("product", [{}])
        product_data = product[0] if isinstance(product, list) and product else product

        score_val = None
        score_models = product_data.get("scoreModel", [{}])
        if score_models:
            score_val = score_models[0].get("score", {}).get("results")

        return {
            "bureau": "transunion",
            "client_id": client_id,
            "report_date": datetime.now(timezone.utc).isoformat(),
            "score": score_val,
            "tradelines": product_data.get("tradeline", []),
            "inquiries": product_data.get("inquiry", []),
            "public_records": product_data.get("publicRecord", []),
            "disputes": product_data.get("dispute", []),
            "collections": product_data.get("collection", []),
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
        """File an FCRA dispute with TransUnion."""
        self._validate_consumer(consumer, require_address=False)

        payload = {
            "dispute": {
                "consumer": {
                    "ssn": consumer["ssn"].replace("-", ""),
                    "firstName": consumer["first_name"],
                    "lastName": consumer["last_name"],
                    "dob": consumer.get("dob", ""),
                },
                "items": [{
                    "itemId": item_id,
                    "disputeReason": reason,
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
            raise DisputeError(f"TransUnion dispute submission failed: {exc}") from exc

        case_number = (
            raw.get("confirmationNumber")
            or raw.get("caseNumber")
            or raw.get("disputeId")
        )
        if not case_number:
            raise DisputeError("TransUnion dispute response missing confirmation number")

        filed_at = datetime.now(timezone.utc)
        return {
            "bureau": "transunion",
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
        """Check status of a previously filed TransUnion dispute."""
        raw = self._request(
            "GET", f"/disputes/{case_number}",
            client_id=client_id, operation="get_dispute_status",
            params={"ssn": ssn.replace("-", "")},
        )
        self._require_fields(raw, "status")

        return {
            "bureau": "transunion",
            "client_id": client_id,
            "case_number": case_number,
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
        """Poll TransUnion for changes to a consumer's credit file."""
        raw = self._request(
            "GET", "/monitoring/changes",
            client_id=client_id, operation="monitor_changes",
            params={"ssn": ssn.replace("-", ""), "monitoringType": monitoring_type},
        )
        changes = raw.get("changes", raw.get("creditFileChanges", []))
        return {
            "bureau": "transunion",
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
        """Return True if the TransUnion API is reachable."""
        try:
            self._get_token()
            resp = self._session.get(
                f"{self.base_url}/health",
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            logger.warning("TransUnion health check failed", exc_info=True)
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
