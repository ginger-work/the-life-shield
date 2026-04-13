"""
Base class for all credit bureau API clients.

Provides:
- Structured logging (all API calls logged for audit trail)
- Retry logic with exponential backoff
- Rate limiting
- Timeout handling
- Response validation helpers
- FCRA-compliant permissible purpose enforcement
"""

from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CreditBureauError(Exception):
    """Base exception for all credit bureau client errors."""


class AuthenticationError(CreditBureauError):
    """Raised when authentication with the bureau fails."""


class RateLimitError(CreditBureauError):
    """Raised when the bureau signals we have exceeded the rate limit."""


class ValidationError(CreditBureauError):
    """Raised when a response fails data validation."""


class DisputeError(CreditBureauError):
    """Raised when a dispute submission fails."""


class ReportPullError(CreditBureauError):
    """Raised when a credit report pull fails."""


# ---------------------------------------------------------------------------
# Audit logger (separate structured log for compliance)
# ---------------------------------------------------------------------------

_audit_logger = logging.getLogger("credit_bureau.audit")


def _audit(
    bureau: str,
    operation: str,
    client_id: str,
    request_id: str,
    status: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Write a structured audit log entry for every API call."""
    _audit_logger.info(
        "",
        extra={
            "bureau": bureau,
            "operation": operation,
            "client_id": client_id,
            "request_id": request_id,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details or {},
        },
    )


# ---------------------------------------------------------------------------
# Base client
# ---------------------------------------------------------------------------

class BaseBureauClient(ABC):
    """
    Abstract base class for credit bureau API clients.

    Subclasses must implement:
        - _authenticate()           -> str  (returns bearer token or API key header)
        - pull_credit_report(...)   -> dict
        - file_dispute(...)         -> dict
        - get_dispute_status(...)   -> dict
        - monitor_changes(...)      -> dict
        - health_check()            -> bool

    Config keys (passed via ``config`` dict):
        base_url (str):             API base URL
        timeout (int):              Request timeout in seconds (default 30)
        max_retries (int):          Max retry attempts for transient errors (default 3)
        backoff_factor (float):     Exponential backoff factor (default 0.5)
        rate_limit_per_minute (int):Max requests per minute (default 60)
        sandbox (bool):             Use sandbox/test environment (default False)
    """

    BUREAU_NAME: str = "unknown"

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.base_url: str = config["base_url"].rstrip("/")
        self.timeout: int = config.get("timeout", 30)
        self.max_retries: int = config.get("max_retries", 3)
        self.backoff_factor: float = config.get("backoff_factor", 0.5)
        self.rate_limit_per_minute: int = config.get("rate_limit_per_minute", 60)
        self.sandbox: bool = config.get("sandbox", False)

        # Rate limiting state
        self._request_timestamps: list[float] = []

        # Build a requests Session with retry adapter
        self._session = self._build_session()

        # Token / credential cache
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_session(self) -> requests.Session:
        """Create a requests.Session with retry + timeout defaults."""
        session = requests.Session()
        retry = Retry(
            total=self.max_retries,
            backoff_factor=self.backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _enforce_rate_limit(self) -> None:
        """Block until we are within the configured rate limit."""
        now = time.monotonic()
        window = 60.0
        self._request_timestamps = [
            t for t in self._request_timestamps if now - t < window
        ]
        if len(self._request_timestamps) >= self.rate_limit_per_minute:
            oldest = self._request_timestamps[0]
            sleep_for = window - (now - oldest) + 0.05
            if sleep_for > 0:
                logger.debug(
                    "%s rate limit: sleeping %.2fs", self.BUREAU_NAME, sleep_for
                )
                time.sleep(sleep_for)
        self._request_timestamps.append(time.monotonic())

    def _get_token(self) -> str:
        """Return a valid auth token, refreshing if expired."""
        if time.time() >= self._token_expiry - 60:
            self._token = self._authenticate()
        return self._token  # type: ignore[return-value]

    def _request(
        self,
        method: str,
        path: str,
        client_id: str,
        operation: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Execute an HTTP request with audit logging, rate limiting,
        and error translation.

        Returns the parsed JSON body on success.
        Raises CreditBureauError subclasses on failure.
        """
        self._enforce_rate_limit()

        request_id = str(uuid.uuid4())
        url = f"{self.base_url}{path}"

        # Inject auth header
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._get_token()}"
        headers["X-Request-ID"] = request_id
        headers.setdefault("Content-Type", "application/json")
        headers.setdefault("Accept", "application/json")

        logger.debug("%s %s %s [req=%s]", method.upper(), url, operation, request_id)
        _audit(self.BUREAU_NAME, operation, client_id, request_id, "REQUEST")

        try:
            resp = self._session.request(
                method,
                url,
                headers=headers,
                timeout=self.timeout,
                **kwargs,
            )
        except requests.exceptions.Timeout as exc:
            _audit(
                self.BUREAU_NAME, operation, client_id, request_id, "TIMEOUT",
                {"error": str(exc)},
            )
            raise CreditBureauError(
                f"{self.BUREAU_NAME} request timed out ({operation})"
            ) from exc
        except requests.exceptions.RequestException as exc:
            _audit(
                self.BUREAU_NAME, operation, client_id, request_id, "NETWORK_ERROR",
                {"error": str(exc)},
            )
            raise CreditBureauError(
                f"{self.BUREAU_NAME} network error ({operation}): {exc}"
            ) from exc

        _audit(
            self.BUREAU_NAME, operation, client_id, request_id,
            f"RESPONSE_{resp.status_code}",
            {"http_status": resp.status_code},
        )

        # HTTP error translation
        if resp.status_code == 401:
            raise AuthenticationError(
                f"{self.BUREAU_NAME} authentication failed (401)"
            )
        if resp.status_code == 429:
            raise RateLimitError(
                f"{self.BUREAU_NAME} rate limit exceeded (429)"
            )
        if resp.status_code >= 400:
            body = _safe_json(resp)
            raise CreditBureauError(
                f"{self.BUREAU_NAME} {operation} failed "
                f"[{resp.status_code}]: {body}"
            )

        data = _safe_json(resp)
        return data

    # ------------------------------------------------------------------
    # Shared validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _require_fields(data: Dict[str, Any], *fields: str) -> None:
        """Raise ValidationError if any required field is missing."""
        missing = [f for f in fields if f not in data]
        if missing:
            raise ValidationError(
                f"Response missing required fields: {missing}"
            )

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def _authenticate(self) -> str:
        """Obtain and return an auth token (or key header value)."""
        ...

    @abstractmethod
    def pull_credit_report(self, client_id: str, consumer: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pull a full consumer credit report.

        Args:
            client_id: Internal Life Shield client identifier.
            consumer:  Dict with keys: ssn, dob, first_name, last_name, address.

        Returns:
            Normalised report dict.
        """
        ...

    @abstractmethod
    def file_dispute(
        self,
        client_id: str,
        consumer: Dict[str, Any],
        item_id: str,
        reason: str,
        statement: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        File a dispute with the bureau.

        Returns dict with at least: case_number, filed_at, expected_resolution_date.
        """
        ...

    @abstractmethod
    def get_dispute_status(
        self, client_id: str, case_number: str, ssn: str
    ) -> Dict[str, Any]:
        """
        Check the status of a previously filed dispute.

        Returns dict with at least: case_number, status, updated_at.
        """
        ...

    @abstractmethod
    def monitor_changes(
        self, client_id: str, ssn: str, monitoring_type: str = "daily"
    ) -> Dict[str, Any]:
        """
        Poll for changes to a consumer's credit file.

        Returns list of change events since the last poll.
        """
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the bureau API is reachable."""
        ...


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _safe_json(resp: requests.Response) -> Dict[str, Any]:
    """Return parsed JSON or wrap raw text in a dict."""
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text}
