"""
Base Bureau Integration Client

Abstract base class that all credit bureau clients implement.
Provides:
- Standard interface for report pulls, dispute filing, and status monitoring
- Sandbox/live mode toggle (production APIs require partnership agreements)
- Retry logic with exponential backoff
- FCRA-compliant audit logging for every API call
- Error normalization across all three bureaus
"""
from __future__ import annotations

import hashlib
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import httpx
import structlog

log = structlog.get_logger(__name__)


class BureauName(str, Enum):
    EQUIFAX = "equifax"
    EXPERIAN = "experian"
    TRANSUNION = "transunion"


class PullType(str, Enum):
    FULL = "full"           # Full tri-merge report
    SOFT = "soft"           # Soft pull (no score impact)
    MONITORING = "monitoring"  # Monitoring pull


class DisputeStatus(str, Enum):
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    COMPLETED = "completed"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


# ─────────────────────────────────────────────────────────
# Data Transfer Objects
# ─────────────────────────────────────────────────────────

@dataclass
class ConsumerIdentity:
    """PII required to pull a credit report. Encrypted at rest."""
    first_name: str
    last_name: str
    ssn: str                    # Full 9-digit SSN (decrypted at use time only)
    date_of_birth: str          # YYYY-MM-DD
    address_line1: str
    city: str
    state: str                  # 2-letter code
    zip_code: str
    address_line2: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


@dataclass
class ReportPullResult:
    """Normalized result from a credit report pull."""
    bureau: BureauName
    pull_type: PullType
    reference_number: str
    pull_timestamp: datetime
    raw_response: Dict[str, Any]        # Full bureau API response
    parsed_data: Dict[str, Any]         # Normalized data

    # Scores
    credit_score: Optional[int] = None
    score_model: Optional[str] = None
    score_range_min: int = 300
    score_range_max: int = 850

    # Summary
    tradelines_count: int = 0
    negative_items_count: int = 0
    inquiries_count: int = 0
    collections_count: int = 0

    # Status
    success: bool = True
    error_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class Tradeline:
    """Normalized tradeline (account) from a credit report."""
    creditor_name: str
    account_type: str
    status: str
    balance: Optional[float] = None
    credit_limit: Optional[float] = None
    original_amount: Optional[float] = None
    monthly_payment: Optional[float] = None
    account_number_masked: Optional[str] = None
    date_opened: Optional[str] = None
    date_reported: Optional[str] = None
    date_last_active: Optional[str] = None
    date_closed: Optional[str] = None
    payment_history: Optional[Dict[str, str]] = None
    utilization: Optional[float] = None
    is_negative: bool = False
    raw: Optional[Dict[str, Any]] = None


@dataclass
class Inquiry:
    """Normalized inquiry from a credit report."""
    inquirer_name: str
    inquiry_date: str
    is_hard: bool = True
    raw: Optional[Dict[str, Any]] = None


@dataclass
class DisputeFilingRequest:
    """Data needed to file a dispute with a bureau."""
    consumer: ConsumerIdentity
    tradeline_id_at_bureau: str         # Bureau's internal ID for the account
    creditor_name: str
    account_number_masked: str
    dispute_reason_code: str            # Bureau-specific reason code
    dispute_explanation: str            # Letter content / explanation
    supporting_documents: List[str] = field(default_factory=list)  # S3 URLs


@dataclass
class DisputeFilingResult:
    """Result of submitting a dispute to a bureau."""
    bureau: BureauName
    confirmation_number: str
    filed_at: datetime
    expected_response_by: datetime      # Filed date + 30 days per FCRA
    raw_response: Dict[str, Any]
    success: bool = True
    error_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class DisputeStatusResult:
    """Result of checking a dispute's current status at the bureau."""
    bureau: BureauName
    confirmation_number: str
    status: DisputeStatus
    checked_at: datetime
    raw_response: Dict[str, Any]
    outcome: Optional[str] = None       # removed, updated, verified, etc.
    outcome_description: Optional[str] = None
    success: bool = True
    error_code: Optional[str] = None
    error_message: Optional[str] = None


# ─────────────────────────────────────────────────────────
# Retry Logic
# ─────────────────────────────────────────────────────────

RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
RETRY_BASE_DELAY_SECONDS = 1.0


def _should_retry(status_code: int) -> bool:
    return status_code in RETRY_STATUS_CODES


def _retry_delay(attempt: int) -> float:
    """Exponential backoff: 1s, 2s, 4s."""
    return RETRY_BASE_DELAY_SECONDS * (2 ** attempt)


# ─────────────────────────────────────────────────────────
# Abstract Base Client
# ─────────────────────────────────────────────────────────

class BaseBureauClient(ABC):
    """
    Abstract base for all three credit bureau clients.

    Subclasses implement the bureau-specific API contract.
    The base class handles:
    - HTTP session management
    - Retry logic
    - Sandbox vs live mode
    - Structured logging (no PII in logs)
    - Error normalization
    """

    bureau_name: BureauName  # Override in subclass
    sandbox_base_url: str    # Override in subclass
    live_base_url: str       # Override in subclass

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        sandbox: bool = True,
        timeout_seconds: int = 30,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.sandbox = sandbox
        self.timeout_seconds = timeout_seconds
        self.base_url = self.sandbox_base_url if sandbox else self.live_base_url

        self._client: Optional[httpx.Client] = None

        if self.sandbox:
            log.info(
                "bureau_client_sandbox_mode",
                bureau=self.bureau_name.value,
                base_url=self.base_url,
            )

    # ── HTTP Session ──────────────────────────────────────

    def _get_client(self) -> httpx.Client:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout_seconds),
                headers=self._default_headers(),
            )
        return self._client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            self._client.close()

    def __enter__(self) -> "BaseBureauClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ── Abstract methods — subclasses implement these ─────

    @abstractmethod
    def _default_headers(self) -> Dict[str, str]:
        """Return auth headers for this bureau."""
        ...

    @abstractmethod
    def _pull_report_request(
        self,
        consumer: ConsumerIdentity,
        pull_type: PullType,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Return (endpoint_path, request_body) for a report pull.
        No HTTP call here — just builds the request.
        """
        ...

    @abstractmethod
    def _parse_report_response(
        self,
        response_data: Dict[str, Any],
        pull_type: PullType,
    ) -> ReportPullResult:
        """Parse the bureau's raw response into a normalized ReportPullResult."""
        ...

    @abstractmethod
    def _file_dispute_request(
        self,
        request: DisputeFilingRequest,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Return (endpoint_path, request_body) for dispute filing.
        """
        ...

    @abstractmethod
    def _parse_dispute_response(
        self,
        response_data: Dict[str, Any],
    ) -> DisputeFilingResult:
        """Parse the bureau's dispute filing response."""
        ...

    @abstractmethod
    def _get_dispute_status_request(
        self,
        confirmation_number: str,
    ) -> Tuple[str, Dict]:
        """Return (endpoint_path, query_params) for dispute status check."""
        ...

    @abstractmethod
    def _parse_dispute_status_response(
        self,
        response_data: Dict[str, Any],
        confirmation_number: str,
    ) -> DisputeStatusResult:
        """Parse the bureau's dispute status response."""
        ...

    # ── Public API ────────────────────────────────────────

    def pull_report(
        self,
        consumer: ConsumerIdentity,
        pull_type: PullType = PullType.FULL,
        correlation_id: Optional[str] = None,
    ) -> ReportPullResult:
        """
        Pull a credit report for the given consumer.

        In sandbox mode, returns realistic mock data without calling the bureau API.
        In live mode, calls the actual bureau API.

        Args:
            consumer: Consumer identity (PII) — not logged
            pull_type: Type of pull (full, soft, monitoring)
            correlation_id: Request correlation ID for tracing

        Returns:
            ReportPullResult with normalized data
        """
        corr_id = correlation_id or str(uuid.uuid4())

        log.info(
            "bureau_pull_report_start",
            bureau=self.bureau_name.value,
            pull_type=pull_type.value,
            sandbox=self.sandbox,
            correlation_id=corr_id,
        )

        if self.sandbox:
            return self._sandbox_pull_report(consumer, pull_type, corr_id)

        endpoint, body = self._pull_report_request(consumer, pull_type)
        response_data = self._http_post(endpoint, body, correlation_id=corr_id)

        result = self._parse_report_response(response_data, pull_type)

        log.info(
            "bureau_pull_report_complete",
            bureau=self.bureau_name.value,
            success=result.success,
            score=result.credit_score,
            tradelines=result.tradelines_count,
            correlation_id=corr_id,
        )
        return result

    def file_dispute(
        self,
        request: DisputeFilingRequest,
        correlation_id: Optional[str] = None,
    ) -> DisputeFilingResult:
        """
        File a dispute with the bureau.

        In sandbox mode, simulates a successful filing.
        In live mode, submits to the actual bureau API.
        """
        corr_id = correlation_id or str(uuid.uuid4())

        log.info(
            "bureau_file_dispute_start",
            bureau=self.bureau_name.value,
            creditor=request.creditor_name,
            reason_code=request.dispute_reason_code,
            sandbox=self.sandbox,
            correlation_id=corr_id,
        )

        if self.sandbox:
            return self._sandbox_file_dispute(request, corr_id)

        endpoint, body = self._file_dispute_request(request)
        response_data = self._http_post(endpoint, body, correlation_id=corr_id)

        result = self._parse_dispute_response(response_data)

        log.info(
            "bureau_file_dispute_complete",
            bureau=self.bureau_name.value,
            confirmation_number=result.confirmation_number,
            success=result.success,
            correlation_id=corr_id,
        )
        return result

    def get_dispute_status(
        self,
        confirmation_number: str,
        correlation_id: Optional[str] = None,
    ) -> DisputeStatusResult:
        """Check the status of a previously filed dispute."""
        corr_id = correlation_id or str(uuid.uuid4())

        log.info(
            "bureau_dispute_status_check",
            bureau=self.bureau_name.value,
            confirmation_number=confirmation_number,
            sandbox=self.sandbox,
            correlation_id=corr_id,
        )

        if self.sandbox:
            return self._sandbox_get_dispute_status(confirmation_number, corr_id)

        endpoint, params = self._get_dispute_status_request(confirmation_number)
        response_data = self._http_get(endpoint, params=params, correlation_id=corr_id)

        result = self._parse_dispute_status_response(response_data, confirmation_number)

        log.info(
            "bureau_dispute_status_result",
            bureau=self.bureau_name.value,
            status=result.status.value,
            correlation_id=corr_id,
        )
        return result

    # ── HTTP helpers (with retry) ─────────────────────────

    def _http_post(
        self,
        endpoint: str,
        body: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST with retry logic. Returns parsed JSON body."""
        client = self._get_client()
        headers = {"X-Correlation-ID": correlation_id} if correlation_id else {}

        for attempt in range(MAX_RETRIES):
            try:
                response = client.post(endpoint, json=body, headers=headers)
                if _should_retry(response.status_code) and attempt < MAX_RETRIES - 1:
                    delay = _retry_delay(attempt)
                    log.warning(
                        "bureau_http_retry",
                        bureau=self.bureau_name.value,
                        endpoint=endpoint,
                        status_code=response.status_code,
                        attempt=attempt + 1,
                        retry_in=delay,
                    )
                    time.sleep(delay)
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException as exc:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(_retry_delay(attempt))
                    continue
                raise BureauTimeoutError(
                    f"{self.bureau_name.value} API timed out after {self.timeout_seconds}s"
                ) from exc
            except httpx.HTTPStatusError as exc:
                raise BureauAPIError(
                    bureau=self.bureau_name.value,
                    status_code=exc.response.status_code,
                    message=str(exc),
                ) from exc

        raise BureauAPIError(
            bureau=self.bureau_name.value,
            status_code=500,
            message="Max retries exceeded",
        )

    def _http_get(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """GET with retry logic. Returns parsed JSON body."""
        client = self._get_client()
        headers = {"X-Correlation-ID": correlation_id} if correlation_id else {}

        for attempt in range(MAX_RETRIES):
            try:
                response = client.get(endpoint, params=params, headers=headers)
                if _should_retry(response.status_code) and attempt < MAX_RETRIES - 1:
                    time.sleep(_retry_delay(attempt))
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException as exc:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(_retry_delay(attempt))
                    continue
                raise BureauTimeoutError(
                    f"{self.bureau_name.value} API timed out"
                ) from exc
            except httpx.HTTPStatusError as exc:
                raise BureauAPIError(
                    bureau=self.bureau_name.value,
                    status_code=exc.response.status_code,
                    message=str(exc),
                ) from exc

        raise BureauAPIError(
            bureau=self.bureau_name.value,
            status_code=500,
            message="Max retries exceeded",
        )

    # ── Sandbox implementations ───────────────────────────

    def _sandbox_pull_report(
        self,
        consumer: ConsumerIdentity,
        pull_type: PullType,
        correlation_id: str,
    ) -> ReportPullResult:
        """
        Return a realistic sandbox report.

        Sandbox data is deterministic based on SSN last 4 digits:
        - SSN ending in 0000-3333: Excellent credit (750+)
        - SSN ending in 3334-6666: Fair credit (580-699)
        - SSN ending in 6667-9999: Poor credit (300-579) with negatives
        """
        ssn_last4 = int(consumer.ssn[-4:]) if consumer.ssn else 5000
        score, scenario = self._sandbox_credit_scenario(ssn_last4)

        ref_number = f"SANDBOX-{self.bureau_name.value.upper()[:3]}-{str(uuid.uuid4())[:8].upper()}"

        tradelines = self._sandbox_tradelines(scenario)
        inquiries = self._sandbox_inquiries(scenario)
        negatives = [t for t in tradelines if t.is_negative]

        parsed = {
            "consumer": {
                "name": f"{consumer.first_name} {consumer.last_name}",
                "address": f"{consumer.address_line1}, {consumer.city}, {consumer.state}",
            },
            "score": {
                "value": score,
                "model": "VantageScore 3.0",
                "range_min": 300,
                "range_max": 850,
            },
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
                    "payment_history": t.payment_history,
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
            "negative_items": [
                {
                    "creditor_name": t.creditor_name,
                    "status": t.status,
                    "balance": t.balance,
                }
                for t in negatives
            ],
        }

        return ReportPullResult(
            bureau=self.bureau_name,
            pull_type=pull_type,
            reference_number=ref_number,
            pull_timestamp=datetime.now(timezone.utc),
            raw_response={"sandbox": True, "data": parsed},
            parsed_data=parsed,
            credit_score=score,
            score_model="VantageScore 3.0",
            score_range_min=300,
            score_range_max=850,
            tradelines_count=len(tradelines),
            negative_items_count=len(negatives),
            inquiries_count=len(inquiries),
            collections_count=sum(1 for t in tradelines if t.account_type == "collection"),
            success=True,
        )

    def _sandbox_credit_scenario(self, ssn_last4: int) -> Tuple[int, str]:
        if ssn_last4 <= 3333:
            return 762, "excellent"
        elif ssn_last4 <= 6666:
            return 638, "fair"
        else:
            return 524, "poor"

    def _sandbox_tradelines(self, scenario: str) -> List[Tradeline]:
        base_lines = [
            Tradeline(
                creditor_name="Chase Bank",
                account_type="credit_card",
                status="current",
                balance=1200.00,
                credit_limit=5000.00,
                account_number_masked="****4521",
                date_opened="2020-03-15",
                date_reported="2026-03-01",
                utilization=24.0,
                payment_history={"2026-03": "OK", "2026-02": "OK", "2026-01": "OK"},
                is_negative=False,
            ),
            Tradeline(
                creditor_name="Capital One",
                account_type="credit_card",
                status="current",
                balance=800.00,
                credit_limit=3000.00,
                account_number_masked="****7890",
                date_opened="2019-07-22",
                date_reported="2026-03-01",
                utilization=26.7,
                payment_history={"2026-03": "OK", "2026-02": "OK"},
                is_negative=False,
            ),
        ]

        if scenario in ("fair", "poor"):
            base_lines.append(
                Tradeline(
                    creditor_name="Santander Consumer USA",
                    account_type="auto_loan",
                    status="late_30",
                    balance=8500.00,
                    credit_limit=None,
                    original_amount=15000.00,
                    account_number_masked="****3312",
                    date_opened="2022-01-10",
                    date_reported="2026-02-15",
                    is_negative=True,
                    payment_history={"2026-02": "LATE_30", "2026-01": "OK"},
                )
            )

        if scenario == "poor":
            base_lines.extend([
                Tradeline(
                    creditor_name="Midland Credit Management",
                    account_type="collection",
                    status="collection",
                    balance=2300.00,
                    credit_limit=None,
                    original_amount=2300.00,
                    account_number_masked="****0045",
                    date_opened="2023-06-01",
                    date_reported="2026-01-10",
                    is_negative=True,
                ),
                Tradeline(
                    creditor_name="Synchrony Bank",
                    account_type="credit_card",
                    status="charge_off",
                    balance=1800.00,
                    credit_limit=2000.00,
                    account_number_masked="****8821",
                    date_opened="2018-11-05",
                    date_reported="2025-12-01",
                    is_negative=True,
                    payment_history={"2025-12": "CHARGEOFF"},
                ),
            ])

        return base_lines

    def _sandbox_inquiries(self, scenario: str) -> List[Inquiry]:
        inquiries = [
            Inquiry(
                inquirer_name="Chase Bank",
                inquiry_date="2025-09-15",
                is_hard=True,
            ),
        ]
        if scenario == "poor":
            inquiries.extend([
                Inquiry(inquirer_name="Capital One", inquiry_date="2025-10-02", is_hard=True),
                Inquiry(inquirer_name="Discover", inquiry_date="2025-11-18", is_hard=True),
            ])
        return inquiries

    def _sandbox_file_dispute(
        self,
        request: DisputeFilingRequest,
        correlation_id: str,
    ) -> DisputeFilingResult:
        """Return a successful sandbox dispute filing result."""
        confirmation = f"SANDBOX-DISP-{self.bureau_name.value.upper()[:3]}-{str(uuid.uuid4())[:10].upper()}"
        now = datetime.now(timezone.utc)
        expected = now + timedelta(days=30)

        log.info(
            "bureau_sandbox_dispute_filed",
            bureau=self.bureau_name.value,
            confirmation_number=confirmation,
            expected_response_by=expected.isoformat(),
            correlation_id=correlation_id,
        )

        return DisputeFilingResult(
            bureau=self.bureau_name,
            confirmation_number=confirmation,
            filed_at=now,
            expected_response_by=expected,
            raw_response={"sandbox": True, "confirmation": confirmation, "status": "submitted"},
            success=True,
        )

    def _sandbox_get_dispute_status(
        self,
        confirmation_number: str,
        correlation_id: str,
    ) -> DisputeStatusResult:
        """Return a sandbox dispute status. Progresses based on time."""
        # Determine status from confirmation number suffix for determinism
        suffix = confirmation_number[-3:] if len(confirmation_number) >= 3 else "AAA"
        char_sum = sum(ord(c) for c in suffix) % 4
        statuses = [
            (DisputeStatus.SUBMITTED, None),
            (DisputeStatus.INVESTIGATING, None),
            (DisputeStatus.COMPLETED, "removed"),
            (DisputeStatus.COMPLETED, "verified"),
        ]
        status, outcome = statuses[char_sum]

        return DisputeStatusResult(
            bureau=self.bureau_name,
            confirmation_number=confirmation_number,
            status=status,
            checked_at=datetime.now(timezone.utc),
            raw_response={"sandbox": True, "status": status.value, "outcome": outcome},
            outcome=outcome,
            outcome_description=(
                "Item successfully removed from credit report" if outcome == "removed"
                else ("Item was verified as accurate" if outcome == "verified" else None)
            ),
            success=True,
        )


# ─────────────────────────────────────────────────────────
# Custom Exceptions
# ─────────────────────────────────────────────────────────

class BureauError(Exception):
    """Base class for bureau integration errors."""
    pass


class BureauAPIError(BureauError):
    """HTTP error response from bureau API."""
    def __init__(self, bureau: str, status_code: int, message: str):
        self.bureau = bureau
        self.status_code = status_code
        self.message = message
        super().__init__(f"[{bureau}] HTTP {status_code}: {message}")


class BureauTimeoutError(BureauError):
    """Bureau API request timed out."""
    pass


class BureauAuthError(BureauError):
    """Authentication failed with bureau API."""
    pass


class BureauRateLimitError(BureauError):
    """Bureau API rate limit exceeded."""
    pass
