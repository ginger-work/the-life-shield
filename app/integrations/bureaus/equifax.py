"""
Equifax Credit Bureau Integration Client

API: Equifax Developer Platform (https://developer.equifax.com)
Auth: OAuth 2.0 (Client Credentials)
Sandbox: Available via developer registration
Production: Requires Equifax partnership agreement + FCRA certification

Dispute reason codes:
- 001: Not mine
- 002: Never late
- 003: Inaccurate information
- 004: Incorrect balance
- 005: Fraudulent account
- 006: Account closed
- 007: Duplicate
- 008: Obsolete (past 7 years)
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import httpx
import structlog

from .base import (
    BaseBureauClient,
    BureauAuthError,
    BureauName,
    ConsumerIdentity,
    DisputeFilingRequest,
    DisputeFilingResult,
    DisputeStatus,
    DisputeStatusResult,
    PullType,
    ReportPullResult,
    Tradeline,
    Inquiry,
)

log = structlog.get_logger(__name__)


# Equifax dispute reason code mapping from our internal codes
DISPUTE_REASON_MAP = {
    "not_mine": "001",
    "inaccurate": "003",
    "wrong_balance": "004",
    "fraudulent": "005",
    "wrong_status": "003",
    "duplicate": "007",
    "obsolete": "008",
    "incomplete": "003",
    "unverifiable": "003",
}


class EquifaxClient(BaseBureauClient):
    """
    Equifax API client.

    Handles:
    - OAuth 2.0 token acquisition and refresh
    - Credit report pulls (full and soft)
    - Dispute filing
    - Dispute status monitoring

    In sandbox mode: returns deterministic mock data.
    In live mode: calls Equifax Developer API.
    """

    bureau_name = BureauName.EQUIFAX
    sandbox_base_url = "https://api.sandbox.equifax.com"
    live_base_url = "https://api.equifax.com"

    # OAuth token endpoint
    TOKEN_ENDPOINT = "/v1/oauth/token"

    # Credit report endpoint (Equifax Consumer Credit Report v6)
    REPORT_ENDPOINT = "/business/consumer-credit/v6/report"

    # Online Disputes API
    DISPUTE_ENDPOINT = "/business/online-disputes/v2/disputes"
    DISPUTE_STATUS_ENDPOINT = "/business/online-disputes/v2/disputes/{confirmation_number}"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        sandbox: bool = True,
        timeout_seconds: int = 30,
    ):
        super().__init__(
            api_key=client_id,
            api_secret=client_secret,
            sandbox=sandbox,
            timeout_seconds=timeout_seconds,
        )
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[float] = None

    # ── Auth ──────────────────────────────────────────────

    def _get_access_token(self) -> str:
        """Acquire or return cached OAuth 2.0 access token."""
        import time

        if self._access_token and self._token_expires_at and time.time() < self._token_expires_at - 60:
            return self._access_token

        if not self.api_key or not self.api_secret:
            if self.sandbox:
                self._access_token = "sandbox-equifax-token"
                self._token_expires_at = time.time() + 3600
                return self._access_token
            raise BureauAuthError("Equifax client_id and client_secret are required in live mode")

        credentials = base64.b64encode(f"{self.api_key}:{self.api_secret}".encode()).decode()

        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
                response = client.post(
                    self.TOKEN_ENDPOINT,
                    headers={
                        "Authorization": f"Basic {credentials}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={"grant_type": "client_credentials"},
                )
                response.raise_for_status()
                token_data = response.json()

                self._access_token = token_data["access_token"]
                self._token_expires_at = time.time() + token_data.get("expires_in", 3600)
                return self._access_token
        except httpx.HTTPStatusError as exc:
            raise BureauAuthError(f"Equifax OAuth failed: {exc.response.status_code}") from exc

    def _default_headers(self) -> Dict[str, str]:
        token = self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ── Report Pull ───────────────────────────────────────

    def _pull_report_request(
        self,
        consumer: ConsumerIdentity,
        pull_type: PullType,
    ) -> Tuple[str, Dict[str, Any]]:
        """Build Equifax Consumer Credit Report request body."""
        # Equifax uses FFIEC-formatted consumer identity
        body = {
            "consumers": {
                "name": [
                    {
                        "firstName": consumer.first_name,
                        "lastName": consumer.last_name,
                    }
                ],
                "ssn": consumer.ssn,
                "dateOfBirth": consumer.date_of_birth,  # YYYY-MM-DD
                "addresses": [
                    {
                        "houseNumber": "",
                        "streetName": consumer.address_line1,
                        "city": consumer.city,
                        "state": consumer.state,
                        "zip": consumer.zip_code,
                        "addressType": "current",
                    }
                ],
            },
            "featuresToInclude": self._features_for_pull_type(pull_type),
        }
        return self.REPORT_ENDPOINT, body

    def _features_for_pull_type(self, pull_type: PullType) -> list:
        """Map pull type to Equifax feature flags."""
        base_features = ["CREDIT_SCORE", "TRADELINES", "INQUIRIES"]
        if pull_type == PullType.FULL:
            return base_features + ["PUBLIC_RECORDS", "COLLECTIONS", "SUMMARY"]
        elif pull_type == PullType.SOFT:
            return ["CREDIT_SCORE", "SUMMARY"]
        elif pull_type == PullType.MONITORING:
            return base_features
        return base_features

    def _parse_report_response(
        self,
        response_data: Dict[str, Any],
        pull_type: PullType,
    ) -> ReportPullResult:
        """Parse Equifax API response into ReportPullResult."""
        import uuid

        consumers = response_data.get("consumers", {})
        tradelines_raw = consumers.get("tradelines", [])
        inquiries_raw = consumers.get("inquiries", [])
        scores_raw = consumers.get("creditProfile", {}).get("scoring", [])

        # Parse score
        credit_score = None
        score_model = None
        if scores_raw:
            first_score = scores_raw[0]
            credit_score = first_score.get("scoreValue")
            score_model = first_score.get("scoreName", "Equifax Credit Score")

        # Parse tradelines
        tradelines = []
        for t in tradelines_raw:
            tradelines.append(Tradeline(
                creditor_name=t.get("creditorName", ""),
                account_type=t.get("type", "").lower(),
                status=t.get("status", "").lower(),
                balance=float(t.get("balance", 0)) if t.get("balance") else None,
                credit_limit=float(t.get("creditLimit", 0)) if t.get("creditLimit") else None,
                account_number_masked=t.get("accountNumber", ""),
                date_opened=t.get("dateOpened"),
                date_reported=t.get("dateReported"),
                is_negative=(t.get("status", "").upper() in ["COLLECTION", "CHARGEOFF", "DEROGATORY"]),
                raw=t,
            ))

        # Parse inquiries
        inquiries = []
        for i in inquiries_raw:
            inquiries.append(Inquiry(
                inquirer_name=i.get("subscriberName", ""),
                inquiry_date=i.get("date", ""),
                is_hard=(i.get("type", "").upper() == "HARD"),
                raw=i,
            ))

        negatives = [t for t in tradelines if t.is_negative]
        collections = [t for t in tradelines if t.account_type == "collection"]

        parsed = {
            "tradelines": [
                {
                    "creditor_name": t.creditor_name,
                    "account_type": t.account_type,
                    "status": t.status,
                    "balance": t.balance,
                    "credit_limit": t.credit_limit,
                    "account_number_masked": t.account_number_masked,
                    "date_opened": t.date_opened,
                    "date_reported": t.date_reported,
                    "is_negative": t.is_negative,
                }
                for t in tradelines
            ],
            "inquiries": [
                {
                    "inquirer_name": i.inquirer_name,
                    "inquiry_date": i.inquiry_date,
                    "is_hard": i.is_hard,
                }
                for i in inquiries
            ],
            "score": {
                "value": credit_score,
                "model": score_model,
            },
        }

        return ReportPullResult(
            bureau=BureauName.EQUIFAX,
            pull_type=pull_type,
            reference_number=response_data.get("referenceNumber", str(uuid.uuid4())),
            pull_timestamp=datetime.now(timezone.utc),
            raw_response=response_data,
            parsed_data=parsed,
            credit_score=credit_score,
            score_model=score_model,
            tradelines_count=len(tradelines),
            negative_items_count=len(negatives),
            inquiries_count=len(inquiries),
            collections_count=len(collections),
            success=True,
        )

    # ── Dispute Filing ────────────────────────────────────

    def _file_dispute_request(
        self,
        request: DisputeFilingRequest,
    ) -> Tuple[str, Dict[str, Any]]:
        """Build Equifax Online Disputes API request."""
        reason_code = DISPUTE_REASON_MAP.get(request.dispute_reason_code, "003")

        body = {
            "applicant": {
                "name": {
                    "firstName": request.consumer.first_name,
                    "lastName": request.consumer.last_name,
                },
                "ssn": request.consumer.ssn,
                "dateOfBirth": request.consumer.date_of_birth,
                "address": {
                    "streetAddress": request.consumer.address_line1,
                    "city": request.consumer.city,
                    "state": request.consumer.state,
                    "postalCode": request.consumer.zip_code,
                },
            },
            "disputeItems": [
                {
                    "disputeType": "TRADELINE",
                    "tradeline": {
                        "creditorName": request.creditor_name,
                        "accountNumber": request.account_number_masked,
                    },
                    "reasonCode": reason_code,
                    "explanation": request.dispute_explanation[:2000],  # Equifax max 2000 chars
                }
            ],
        }

        return self.DISPUTE_ENDPOINT, body

    def _parse_dispute_response(
        self,
        response_data: Dict[str, Any],
    ) -> DisputeFilingResult:
        """Parse Equifax dispute filing response."""
        from datetime import timedelta

        confirmation = response_data.get("confirmationNumber", response_data.get("disputeId", ""))
        now = datetime.now(timezone.utc)

        return DisputeFilingResult(
            bureau=BureauName.EQUIFAX,
            confirmation_number=confirmation,
            filed_at=now,
            expected_response_by=now + timedelta(days=30),
            raw_response=response_data,
            success=True,
        )

    # ── Dispute Status ────────────────────────────────────

    def _get_dispute_status_request(
        self,
        confirmation_number: str,
    ) -> Tuple[str, Dict]:
        endpoint = self.DISPUTE_STATUS_ENDPOINT.format(confirmation_number=confirmation_number)
        return endpoint, {}

    def _parse_dispute_status_response(
        self,
        response_data: Dict[str, Any],
        confirmation_number: str,
    ) -> DisputeStatusResult:
        """Parse Equifax dispute status response."""
        raw_status = response_data.get("status", "").upper()
        status_map = {
            "SUBMITTED": DisputeStatus.SUBMITTED,
            "ACKNOWLEDGED": DisputeStatus.ACKNOWLEDGED,
            "IN_REVIEW": DisputeStatus.INVESTIGATING,
            "INVESTIGATING": DisputeStatus.INVESTIGATING,
            "COMPLETED": DisputeStatus.COMPLETED,
            "REJECTED": DisputeStatus.REJECTED,
        }
        status = status_map.get(raw_status, DisputeStatus.UNKNOWN)
        outcome = response_data.get("outcome", response_data.get("result"))

        return DisputeStatusResult(
            bureau=BureauName.EQUIFAX,
            confirmation_number=confirmation_number,
            status=status,
            checked_at=datetime.now(timezone.utc),
            raw_response=response_data,
            outcome=outcome,
            success=True,
        )
