"""
Experian Credit Bureau Integration Client

API: Experian Connect API (https://developer.experian.com)
Auth: OAuth 2.0 (Client Credentials) — same pattern as Equifax
Sandbox: Experian Sandbox environment available
Production: Requires Experian agreement + permissible purpose certification

Key differences from Equifax:
- Uses SUBCODE for subscriber identification
- Different field naming conventions (camelCase variations)
- Dispute system uses Experian's CDII (Consumer Dispute Investigation Initiative) spec
"""
from __future__ import annotations

import base64
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

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


# Experian dispute type codes
DISPUTE_REASON_MAP = {
    "not_mine": "NAM",    # Not my account
    "inaccurate": "INF",  # Inaccurate information
    "wrong_balance": "BAL",  # Balance dispute
    "fraudulent": "FRD",  # Fraudulent/identity theft
    "wrong_status": "STS",  # Wrong status
    "duplicate": "DUP",   # Duplicate account
    "obsolete": "OBS",    # Obsolete (past 7 years)
    "incomplete": "INF",
    "unverifiable": "UNV",  # Cannot be verified
}


class ExperianClient(BaseBureauClient):
    """
    Experian Connect API client.

    Handles credit report pulls, dispute filing, and status monitoring
    via Experian's OAuth 2.0-protected REST APIs.

    Experian uses:
    - Subscriber codes (SUBCODE) for identity
    - CDII-format dispute submissions
    - Polling for dispute status (no webhooks in standard tier)
    """

    bureau_name = BureauName.EXPERIAN
    sandbox_base_url = "https://sandbox.experian.com"
    live_base_url = "https://us-api.experian.com"

    TOKEN_ENDPOINT = "/oauth2/v1/token"
    REPORT_ENDPOINT = "/consumerservices/credit-profile/v2/credit-report"
    DISPUTE_ENDPOINT = "/consumerservices/disputes/v2"
    DISPUTE_STATUS_ENDPOINT = "/consumerservices/disputes/v2/{case_number}"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        subcode: Optional[str] = None,  # Experian-specific: subscriber code
        sandbox: bool = True,
        timeout_seconds: int = 30,
    ):
        super().__init__(
            api_key=client_id,
            api_secret=client_secret,
            sandbox=sandbox,
            timeout_seconds=timeout_seconds,
        )
        self.subcode = subcode
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[float] = None

    # ── Auth ──────────────────────────────────────────────

    def _get_access_token(self) -> str:
        if self._access_token and self._token_expires_at and time.time() < self._token_expires_at - 60:
            return self._access_token

        if not self.api_key or not self.api_secret:
            if self.sandbox:
                self._access_token = "sandbox-experian-token"
                self._token_expires_at = time.time() + 3600
                return self._access_token
            raise BureauAuthError("Experian client_id and client_secret required in live mode")

        import httpx
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
        except Exception as exc:
            raise BureauAuthError(f"Experian OAuth failed: {exc}") from exc

    def _default_headers(self) -> Dict[str, str]:
        token = self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.subcode:
            headers["subcode"] = self.subcode
        return headers

    # ── Report Pull ───────────────────────────────────────

    def _pull_report_request(
        self,
        consumer: ConsumerIdentity,
        pull_type: PullType,
    ) -> Tuple[str, Dict[str, Any]]:
        """Build Experian Credit Report request."""
        # Experian uses a specific consumer identity format
        body = {
            "primaryApplicant": {
                "name": {
                    "firstName": consumer.first_name,
                    "lastName": consumer.last_name,
                },
                "ssn": consumer.ssn,
                "dob": {"dob": consumer.date_of_birth},
                "currentAddress": {
                    "line1": consumer.address_line1,
                    "city": consumer.city,
                    "state": consumer.state,
                    "zipCode": consumer.zip_code,
                },
            },
            "requestType": self._request_type_for_pull(pull_type),
            "reportsRequested": {
                "creditProfile": True,
                "riskModels": pull_type != PullType.SOFT,
                "tradelines": True,
                "inquiries": True,
                "collections": pull_type == PullType.FULL,
            },
        }
        return self.REPORT_ENDPOINT, body

    def _request_type_for_pull(self, pull_type: PullType) -> str:
        mapping = {
            PullType.FULL: "FullProfile",
            PullType.SOFT: "SoftInquiry",
            PullType.MONITORING: "Monitoring",
        }
        return mapping.get(pull_type, "FullProfile")

    def _parse_report_response(
        self,
        response_data: Dict[str, Any],
        pull_type: PullType,
    ) -> ReportPullResult:
        import uuid as _uuid

        credit_profile = response_data.get("creditProfile", {})
        risk_models = response_data.get("riskModels", [{}])
        tradelines_raw = response_data.get("tradelines", [])
        inquiries_raw = response_data.get("inquiries", [])

        # Score
        credit_score = None
        score_model = None
        if risk_models:
            model = risk_models[0]
            credit_score = model.get("score")
            score_model = model.get("modelName", "VantageScore 3.0")

        # Tradelines
        tradelines = []
        for t in tradelines_raw:
            is_neg = t.get("status", "").upper() in (
                "COLLECTION", "CHARGEOFF", "CHARGE_OFF", "DEROGATORY",
                "30DLATE", "60DLATE", "90DLATE",
            )
            tradelines.append(Tradeline(
                creditor_name=t.get("subscriberName", t.get("creditorName", "")),
                account_type=t.get("accountType", "").lower(),
                status=t.get("accountStatus", t.get("status", "")).lower(),
                balance=float(t.get("balanceAmount", 0)) if t.get("balanceAmount") else None,
                credit_limit=float(t.get("creditLimit", 0)) if t.get("creditLimit") else None,
                account_number_masked=t.get("accountNumber", ""),
                date_opened=t.get("openDate"),
                date_reported=t.get("reportedDate"),
                is_negative=is_neg,
                raw=t,
            ))

        # Inquiries
        inquiries = []
        for i in inquiries_raw:
            inquiries.append(Inquiry(
                inquirer_name=i.get("subscriberName", ""),
                inquiry_date=i.get("inquiryDate", ""),
                is_hard=(i.get("inquiryType", "hard").lower() == "hard"),
                raw=i,
            ))

        negatives = [t for t in tradelines if t.is_negative]
        collections = [t for t in tradelines if "collection" in t.account_type.lower()]

        parsed = {
            "score": {"value": credit_score, "model": score_model},
            "tradelines": [
                {
                    "creditor_name": t.creditor_name,
                    "account_type": t.account_type,
                    "status": t.status,
                    "balance": t.balance,
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
        }

        return ReportPullResult(
            bureau=BureauName.EXPERIAN,
            pull_type=pull_type,
            reference_number=response_data.get("referenceId", str(_uuid.uuid4())),
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
        """Build Experian CDII dispute request."""
        dispute_type = DISPUTE_REASON_MAP.get(request.dispute_reason_code, "INF")

        body = {
            "consumer": {
                "name": {
                    "firstName": request.consumer.first_name,
                    "lastName": request.consumer.last_name,
                },
                "ssn": request.consumer.ssn,
                "dateOfBirth": request.consumer.date_of_birth,
                "currentAddress": {
                    "streetAddress": request.consumer.address_line1,
                    "city": request.consumer.city,
                    "state": request.consumer.state,
                    "zipCode": request.consumer.zip_code,
                },
            },
            "disputeItems": [
                {
                    "itemType": "tradeline",
                    "tradeline": {
                        "subscriberCode": "",
                        "subscriberName": request.creditor_name,
                        "accountNumber": request.account_number_masked,
                    },
                    "disputeType": dispute_type,
                    "consumerStatement": request.dispute_explanation[:1500],
                }
            ],
        }
        return self.DISPUTE_ENDPOINT, body

    def _parse_dispute_response(
        self,
        response_data: Dict[str, Any],
    ) -> DisputeFilingResult:
        case_number = response_data.get("caseNumber", response_data.get("confirmationNumber", ""))
        now = datetime.now(timezone.utc)
        return DisputeFilingResult(
            bureau=BureauName.EXPERIAN,
            confirmation_number=case_number,
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
        endpoint = self.DISPUTE_STATUS_ENDPOINT.format(case_number=confirmation_number)
        return endpoint, {}

    def _parse_dispute_status_response(
        self,
        response_data: Dict[str, Any],
        confirmation_number: str,
    ) -> DisputeStatusResult:
        raw_status = response_data.get("caseStatus", response_data.get("status", "")).upper()
        status_map = {
            "OPEN": DisputeStatus.SUBMITTED,
            "IN_PROGRESS": DisputeStatus.INVESTIGATING,
            "INVESTIGATING": DisputeStatus.INVESTIGATING,
            "CLOSED": DisputeStatus.COMPLETED,
            "COMPLETED": DisputeStatus.COMPLETED,
            "REJECTED": DisputeStatus.REJECTED,
        }
        status = status_map.get(raw_status, DisputeStatus.UNKNOWN)
        outcome = response_data.get("caseOutcome", response_data.get("outcome"))

        return DisputeStatusResult(
            bureau=BureauName.EXPERIAN,
            confirmation_number=confirmation_number,
            status=status,
            checked_at=datetime.now(timezone.utc),
            raw_response=response_data,
            outcome=outcome,
            success=True,
        )
