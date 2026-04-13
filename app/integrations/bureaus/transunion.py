"""
TransUnion Credit Bureau Integration Client

API: TransUnion TruVision (https://developer.transunion.com)
Auth: TLS mutual authentication + API key (or OAuth 2.0 depending on product tier)
Sandbox: TransUnion Sandbox available for partners
Production: Requires TransUnion data access agreement

Key differences:
- Uses member code + security code for authentication
- Industry-specific product codes for report pulls
- Dispute API uses CRRNT (Consumer Reinvestigation Request Notification)
- Returns MISMO (Mortgage Industry Standards Maintenance Organization) XML in some endpoints
  — we normalize to JSON in this client
"""
from __future__ import annotations

import base64
import time
import uuid
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


# TransUnion dispute reason codes
DISPUTE_REASON_MAP = {
    "not_mine": "105",         # Account not mine
    "inaccurate": "102",       # Inaccurate information
    "wrong_balance": "110",    # Balance incorrect
    "fraudulent": "107",       # Fraudulent account
    "wrong_status": "104",     # Account status wrong
    "duplicate": "108",        # Duplicate account
    "obsolete": "112",         # Past FCRA reporting limit
    "incomplete": "103",       # Incomplete information
    "unverifiable": "106",     # Cannot verify
}


class TransUnionClient(BaseBureauClient):
    """
    TransUnion TruVision API client.

    Uses either:
    - API key authentication (most common for new integrations)
    - Mutual TLS for higher-tier enterprise partnerships

    This implementation uses the REST/JSON API endpoint.
    """

    bureau_name = BureauName.TRANSUNION
    sandbox_base_url = "https://api-sandbox.transunion.com"
    live_base_url = "https://api.transunion.com"

    TOKEN_ENDPOINT = "/v1/oauth/token"
    REPORT_ENDPOINT = "/v1/consumer-credit/credit-report"
    DISPUTE_ENDPOINT = "/v1/disputes"
    DISPUTE_STATUS_ENDPOINT = "/v1/disputes/{dispute_id}"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        member_code: Optional[str] = None,        # TransUnion-specific
        security_code: Optional[str] = None,      # TransUnion-specific
        sandbox: bool = True,
        timeout_seconds: int = 30,
    ):
        super().__init__(
            api_key=api_key,
            api_secret=api_secret,
            sandbox=sandbox,
            timeout_seconds=timeout_seconds,
        )
        self.member_code = member_code
        self.security_code = security_code
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[float] = None

    # ── Auth ──────────────────────────────────────────────

    def _get_access_token(self) -> str:
        if self._access_token and self._token_expires_at and time.time() < self._token_expires_at - 60:
            return self._access_token

        if not self.api_key or not self.api_secret:
            if self.sandbox:
                self._access_token = "sandbox-transunion-token"
                self._token_expires_at = time.time() + 3600
                return self._access_token
            raise BureauAuthError("TransUnion api_key and api_secret required in live mode")

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
            raise BureauAuthError(f"TransUnion OAuth failed: {exc}") from exc

    def _default_headers(self) -> Dict[str, str]:
        token = self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.member_code:
            headers["X-TU-MemberCode"] = self.member_code
        if self.security_code:
            headers["X-TU-SecurityCode"] = self.security_code
        return headers

    # ── Report Pull ───────────────────────────────────────

    def _pull_report_request(
        self,
        consumer: ConsumerIdentity,
        pull_type: PullType,
    ) -> Tuple[str, Dict[str, Any]]:
        body = {
            "subject": {
                "subjectRecord": {
                    "indicative": {
                        "name": {
                            "firstName": consumer.first_name,
                            "lastName": consumer.last_name,
                        },
                        "socialSecurity": {"number": consumer.ssn},
                        "dateOfBirth": consumer.date_of_birth,
                        "address": {
                            "street": consumer.address_line1,
                            "city": consumer.city,
                            "state": consumer.state,
                            "zipCode": consumer.zip_code,
                            "addressType": "current",
                        },
                    }
                }
            },
            "product": {
                "code": self._product_code_for_pull(pull_type),
                "responseType": "json",
            },
        }
        return self.REPORT_ENDPOINT, body

    def _product_code_for_pull(self, pull_type: PullType) -> str:
        mapping = {
            PullType.FULL: "07000",      # Full consumer report
            PullType.SOFT: "07001",      # Soft inquiry
            PullType.MONITORING: "07002",  # Monitoring
        }
        return mapping.get(pull_type, "07000")

    def _parse_report_response(
        self,
        response_data: Dict[str, Any],
        pull_type: PullType,
    ) -> ReportPullResult:
        """Parse TransUnion response (normalized from MISMO-like format)."""
        # TransUnion wraps most data under creditBureau -> product
        product = response_data.get("creditBureau", {}).get("product", {})
        subject = product.get("subject", {}).get("subjectRecord", {})
        fin = subject.get("fileSummary", {})
        addons = subject.get("addOnProducts", [{}])

        # Score (under addOnProduct[0].scoreModel)
        credit_score = None
        score_model = None
        if addons:
            score_info = addons[0].get("scoreModel", {})
            score_value = score_info.get("score", {}).get("results")
            if score_value:
                credit_score = int(score_value)
                score_model = score_info.get("score", {}).get("scoreName", "TransUnion Credit Score")

        # Tradelines
        tradelines_raw = subject.get("tradeline", [])
        if isinstance(tradelines_raw, dict):
            tradelines_raw = [tradelines_raw]

        tradelines = []
        for t in tradelines_raw:
            status_raw = t.get("accountRating", t.get("payStatus", {}).get("description", ""))
            is_neg = any(
                kw in str(status_raw).upper()
                for kw in ("COLLECTION", "CHARGEOFF", "DEROGATORY", "30", "60", "90", "120")
            )
            tradelines.append(Tradeline(
                creditor_name=t.get("creditorName", t.get("subscriber", {}).get("name", {}).get("unparsed", "")),
                account_type=t.get("portfolioType", t.get("accountType", "")).lower(),
                status=str(status_raw).lower(),
                balance=float(t.get("currentBalance", 0)) if t.get("currentBalance") else None,
                credit_limit=float(t.get("highCredit", 0)) if t.get("highCredit") else None,
                account_number_masked=t.get("accountNumber", ""),
                date_opened=t.get("openDate"),
                date_reported=t.get("dateReported"),
                is_negative=is_neg,
                raw=t,
            ))

        # Inquiries
        inquiries_raw = subject.get("inquiry", [])
        if isinstance(inquiries_raw, dict):
            inquiries_raw = [inquiries_raw]

        inquiries = []
        for i in inquiries_raw:
            inquiries.append(Inquiry(
                inquirer_name=i.get("creditorName", i.get("subscriberName", "")),
                inquiry_date=i.get("date", ""),
                is_hard=(i.get("type", "hard").lower() != "soft"),
                raw=i,
            ))

        negatives = [t for t in tradelines if t.is_negative]
        collections = [t for t in tradelines if "collect" in t.account_type.lower()]

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

        ref_number = (
            fin.get("referenceNumber")
            or response_data.get("referenceNumber")
            or str(uuid.uuid4())
        )

        return ReportPullResult(
            bureau=BureauName.TRANSUNION,
            pull_type=pull_type,
            reference_number=ref_number,
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
        reason_code = DISPUTE_REASON_MAP.get(request.dispute_reason_code, "102")

        body = {
            "consumer": {
                "firstName": request.consumer.first_name,
                "lastName": request.consumer.last_name,
                "ssn": request.consumer.ssn,
                "dateOfBirth": request.consumer.date_of_birth,
                "address": {
                    "streetAddress": request.consumer.address_line1,
                    "city": request.consumer.city,
                    "state": request.consumer.state,
                    "zipCode": request.consumer.zip_code,
                },
            },
            "disputes": [
                {
                    "disputeType": "TRADELINE",
                    "accountInfo": {
                        "creditorName": request.creditor_name,
                        "accountNumber": request.account_number_masked,
                    },
                    "reasonCode": reason_code,
                    "explanation": request.dispute_explanation[:3000],
                }
            ],
            "deliveryMethod": "electronic",
        }
        return self.DISPUTE_ENDPOINT, body

    def _parse_dispute_response(
        self,
        response_data: Dict[str, Any],
    ) -> DisputeFilingResult:
        dispute_id = (
            response_data.get("disputeId")
            or response_data.get("confirmationNumber")
            or str(uuid.uuid4())
        )
        now = datetime.now(timezone.utc)
        return DisputeFilingResult(
            bureau=BureauName.TRANSUNION,
            confirmation_number=dispute_id,
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
        endpoint = self.DISPUTE_STATUS_ENDPOINT.format(dispute_id=confirmation_number)
        return endpoint, {}

    def _parse_dispute_status_response(
        self,
        response_data: Dict[str, Any],
        confirmation_number: str,
    ) -> DisputeStatusResult:
        raw_status = response_data.get("status", response_data.get("disputeStatus", "")).upper()
        status_map = {
            "SUBMITTED": DisputeStatus.SUBMITTED,
            "RECEIVED": DisputeStatus.ACKNOWLEDGED,
            "IN_REVIEW": DisputeStatus.INVESTIGATING,
            "INVESTIGATING": DisputeStatus.INVESTIGATING,
            "COMPLETED": DisputeStatus.COMPLETED,
            "RESOLVED": DisputeStatus.COMPLETED,
            "REJECTED": DisputeStatus.REJECTED,
        }
        status = status_map.get(raw_status, DisputeStatus.UNKNOWN)
        outcome = response_data.get("disputeResult", response_data.get("outcome"))

        return DisputeStatusResult(
            bureau=BureauName.TRANSUNION,
            confirmation_number=confirmation_number,
            status=status,
            checked_at=datetime.now(timezone.utc),
            raw_response=response_data,
            outcome=str(outcome).lower() if outcome else None,
            success=True,
        )
