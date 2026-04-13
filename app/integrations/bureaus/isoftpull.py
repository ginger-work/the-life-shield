"""
iSoftPull Soft-Pull Integration Client

iSoftPull specializes in soft credit inquiries that do NOT impact consumer scores.
Used for real-time credit monitoring and score tracking.

API: https://isoftpull.com/api-docs
Auth: API Key (Bearer token)
Sandbox: Available with test credentials
Production: Partner account required

Use cases:
- Initial intake credit check (doesn't ding the consumer)
- Monthly monitoring pulls
- Score tracking over time
- Identifying newly appearing negatives
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
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


class ISoftPullClient(BaseBureauClient):
    """
    iSoftPull soft-pull credit check client.

    iSoftPull pulls from all three bureaus simultaneously using a single
    soft inquiry, making it ideal for:
    1. Client intake (score without impact)
    2. Monthly monitoring
    3. Score change detection

    Note: iSoftPull does NOT provide dispute filing capability.
    Filing disputes still uses the individual bureau clients.
    """

    bureau_name = BureauName.EQUIFAX  # iSoftPull aggregates all 3; we use EQUIFAX as default
    sandbox_base_url = "https://api-sandbox.isoftpull.com"
    live_base_url = "https://api.isoftpull.com"

    REPORT_ENDPOINT = "/v2/credit/soft-pull"
    MONITORING_ENDPOINT = "/v2/credit/monitoring"
    SCORE_ENDPOINT = "/v2/credit/score"

    def __init__(
        self,
        api_key: Optional[str] = None,
        sandbox: bool = True,
        timeout_seconds: int = 30,
    ):
        super().__init__(
            api_key=api_key,
            api_secret=None,
            sandbox=sandbox,
            timeout_seconds=timeout_seconds,
        )

    # ── Auth ──────────────────────────────────────────────

    def _default_headers(self) -> Dict[str, str]:
        if not self.api_key and not self.sandbox:
            raise BureauAuthError("iSoftPull API key is required in live mode")

        api_key = self.api_key or "sandbox-isoftpull-test-key"
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ── Soft Pull (tri-merge) ─────────────────────────────

    def pull_tri_merge(
        self,
        consumer: ConsumerIdentity,
        correlation_id: Optional[str] = None,
    ) -> Dict[BureauName, ReportPullResult]:
        """
        Pull a tri-merge soft pull from all three bureaus simultaneously.

        Returns a dict keyed by BureauName with individual results.
        This is the primary use case for iSoftPull.
        """
        corr_id = correlation_id or str(uuid.uuid4())

        log.info(
            "isoftpull_tri_merge_start",
            sandbox=self.sandbox,
            correlation_id=corr_id,
        )

        if self.sandbox:
            results = {
                BureauName.EQUIFAX: self._sandbox_pull_report(consumer, PullType.SOFT, corr_id),
                BureauName.EXPERIAN: self._sandbox_pull_report(consumer, PullType.SOFT, corr_id),
                BureauName.TRANSUNION: self._sandbox_pull_report(consumer, PullType.SOFT, corr_id),
            }
            # Override bureau names since base uses self.bureau_name (EQUIFAX) for all
            for bureau, result in results.items():
                result.bureau = bureau
            return results

        # Live mode
        endpoint, body = self._pull_report_request(consumer, PullType.SOFT)
        response_data = self._http_post(endpoint, body, correlation_id=corr_id)

        return self._parse_tri_merge_response(response_data, consumer)

    def pull_monitoring(
        self,
        consumer: ConsumerIdentity,
        correlation_id: Optional[str] = None,
    ) -> Dict[BureauName, Optional[int]]:
        """
        Lightweight monitoring pull — returns scores only, no full report.
        Use monthly for score tracking without cost of full report pull.
        Returns {BureauName: score_or_None}
        """
        corr_id = correlation_id or str(uuid.uuid4())

        if self.sandbox:
            ssn_last4 = int(consumer.ssn[-4:]) if consumer.ssn else 5000
            score, _ = self._sandbox_credit_scenario(ssn_last4)
            # Slightly different scores per bureau for realism
            return {
                BureauName.EQUIFAX: score,
                BureauName.EXPERIAN: score - 3,
                BureauName.TRANSUNION: score + 2,
            }

        endpoint = self.SCORE_ENDPOINT
        body = {
            "consumer": {
                "firstName": consumer.first_name,
                "lastName": consumer.last_name,
                "ssn": consumer.ssn,
                "dateOfBirth": consumer.date_of_birth,
            }
        }
        response_data = self._http_post(endpoint, body, correlation_id=corr_id)
        return self._parse_monitoring_response(response_data)

    # ── Request/Response builders ─────────────────────────

    def _pull_report_request(
        self,
        consumer: ConsumerIdentity,
        pull_type: PullType,
    ) -> Tuple[str, Dict[str, Any]]:
        body = {
            "consumer": {
                "firstName": consumer.first_name,
                "lastName": consumer.last_name,
                "ssn": consumer.ssn,
                "dateOfBirth": consumer.date_of_birth,
                "address": {
                    "line1": consumer.address_line1,
                    "city": consumer.city,
                    "state": consumer.state,
                    "zip": consumer.zip_code,
                },
                "email": consumer.email,
                "phone": consumer.phone,
            },
            "bureaus": ["equifax", "experian", "transunion"],
            "includeScore": True,
            "includeTradelines": True,
            "includeInquiries": True,
            "softPull": True,
        }
        return self.REPORT_ENDPOINT, body

    def _parse_report_response(
        self,
        response_data: Dict[str, Any],
        pull_type: PullType,
    ) -> ReportPullResult:
        """Single-bureau fallback parser (used when tri-merge isn't called)."""
        # iSoftPull returns per-bureau sections
        bureaus = response_data.get("bureaus", {})
        equifax_data = bureaus.get("equifax", {})
        return self._parse_single_bureau_section(equifax_data, BureauName.EQUIFAX, pull_type)

    def _parse_tri_merge_response(
        self,
        response_data: Dict[str, Any],
        consumer: ConsumerIdentity,
    ) -> Dict[BureauName, ReportPullResult]:
        """Parse tri-merge response into per-bureau results."""
        bureaus = response_data.get("bureaus", {})
        results = {}

        for bureau_key, bureau_enum in [
            ("equifax", BureauName.EQUIFAX),
            ("experian", BureauName.EXPERIAN),
            ("transunion", BureauName.TRANSUNION),
        ]:
            bureau_data = bureaus.get(bureau_key, {})
            if bureau_data:
                results[bureau_enum] = self._parse_single_bureau_section(
                    bureau_data, bureau_enum, PullType.SOFT
                )

        return results

    def _parse_single_bureau_section(
        self,
        data: Dict[str, Any],
        bureau: BureauName,
        pull_type: PullType,
    ) -> ReportPullResult:
        credit_score = data.get("creditScore") or data.get("score")
        score_model = data.get("scoreModel", "VantageScore 3.0")

        tradelines_raw = data.get("tradelines", [])
        inquiries_raw = data.get("inquiries", [])

        tradelines = []
        for t in tradelines_raw:
            is_neg = t.get("isNegative", False) or t.get("negative", False)
            tradelines.append(Tradeline(
                creditor_name=t.get("creditorName", ""),
                account_type=t.get("accountType", "").lower(),
                status=t.get("status", "").lower(),
                balance=t.get("balance"),
                credit_limit=t.get("creditLimit"),
                account_number_masked=t.get("accountNumberMasked", ""),
                date_opened=t.get("dateOpened"),
                date_reported=t.get("dateReported"),
                is_negative=is_neg,
            ))

        inquiries = []
        for i in inquiries_raw:
            inquiries.append(Inquiry(
                inquirer_name=i.get("inquirerName", ""),
                inquiry_date=i.get("inquiryDate", ""),
                is_hard=i.get("isHard", True),
            ))

        negatives = [t for t in tradelines if t.is_negative]

        return ReportPullResult(
            bureau=bureau,
            pull_type=pull_type,
            reference_number=data.get("referenceNumber", str(uuid.uuid4())),
            pull_timestamp=datetime.now(timezone.utc),
            raw_response=data,
            parsed_data={
                "score": {"value": credit_score, "model": score_model},
                "tradelines": [{"creditor_name": t.creditor_name, "status": t.status, "is_negative": t.is_negative} for t in tradelines],
                "inquiries": [{"inquirer_name": i.inquirer_name, "inquiry_date": i.inquiry_date} for i in inquiries],
            },
            credit_score=credit_score,
            score_model=score_model,
            tradelines_count=len(tradelines),
            negative_items_count=len(negatives),
            inquiries_count=len(inquiries),
            success=True,
        )

    def _parse_monitoring_response(
        self,
        response_data: Dict[str, Any],
    ) -> Dict[BureauName, Optional[int]]:
        scores = response_data.get("scores", {})
        return {
            BureauName.EQUIFAX: scores.get("equifax"),
            BureauName.EXPERIAN: scores.get("experian"),
            BureauName.TRANSUNION: scores.get("transunion"),
        }

    # ── iSoftPull doesn't support disputes ───────────────

    def file_dispute(self, request: "DisputeFilingRequest", **kwargs) -> "DisputeFilingResult":  # type: ignore[override]
        raise NotImplementedError(
            "iSoftPull does not support dispute filing. "
            "Use EquifaxClient, ExperianClient, or TransUnionClient."
        )

    def get_dispute_status(self, confirmation_number: str, **kwargs) -> "DisputeStatusResult":  # type: ignore[override]
        raise NotImplementedError("iSoftPull does not support dispute status.")

    def _file_dispute_request(self, request: "DisputeFilingRequest") -> Tuple[str, Dict]:
        raise NotImplementedError("iSoftPull does not support dispute filing.")

    def _parse_dispute_response(self, response_data: Dict) -> "DisputeFilingResult":
        raise NotImplementedError("iSoftPull does not support dispute filing.")

    def _get_dispute_status_request(self, confirmation_number: str) -> Tuple[str, Dict]:
        raise NotImplementedError("iSoftPull does not support dispute status.")

    def _parse_dispute_status_response(
        self, response_data: Dict, confirmation_number: str
    ) -> "DisputeStatusResult":
        raise NotImplementedError("iSoftPull does not support dispute status.")
