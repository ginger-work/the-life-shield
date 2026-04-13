"""
Credit Bureau Client Factory — The Life Shield

Factory pattern for instantiating the correct bureau client based on a
bureau name string or the ``Bureau`` enum.  Supports:
- Building from environment variables (recommended for production)
- Building from explicit config dicts (useful for tests / DI)
- Creating a "bundle" with all clients pre-built

Usage::

    from api.credit_bureaus.client_factory import CreditBureauFactory, Bureau

    # --- From environment variables ---
    factory = CreditBureauFactory.from_env()

    equifax = factory.get_client(Bureau.EQUIFAX)
    experian = factory.get_client(Bureau.EXPERIAN)
    transunion = factory.get_client(Bureau.TRANSUNION)
    isoftpull = factory.get_client(Bureau.ISOFTPULL)

    # --- Pull a report via the factory ---
    report = factory.pull_report(
        bureau=Bureau.EQUIFAX,
        client_id="ls-client-001",
        consumer={...},
    )

    # --- File a dispute via the factory ---
    dispute = factory.file_dispute(
        bureau=Bureau.TRANSUNION,
        client_id="ls-client-001",
        consumer={...},
        item_id="TU-123456",
        reason="NOT_MY_ACCOUNT",
    )

    # --- Pull reports from all 3 bureaus concurrently ---
    reports = factory.pull_all_reports(
        client_id="ls-client-001",
        consumer={...},
    )

    # --- Health check all bureaus ---
    status = factory.health_check_all()
    # {"equifax": True, "experian": False, "transunion": True, "isoftpull": True}
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
from typing import Any, Dict, Optional

from .equifax import EquifaxClient
from .experian import ExperianClient
from .isoftpull import iSoftPullClient
from .transunion import TransUnionClient
from .base import BaseBureauClient, CreditBureauError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bureau enum
# ---------------------------------------------------------------------------

class Bureau(str, Enum):
    """Canonical bureau identifiers used throughout The Life Shield."""

    EQUIFAX = "equifax"
    EXPERIAN = "experian"
    TRANSUNION = "transunion"
    ISOFTPULL = "isoftpull"

    @classmethod
    def from_string(cls, value: str) -> "Bureau":
        """
        Resolve a bureau name string to the enum member.

        Raises:
            ValueError: if the name doesn't match a known bureau.
        """
        normalised = value.strip().lower().replace("-", "").replace("_", "")
        mapping = {
            "equifax": cls.EQUIFAX,
            "experian": cls.EXPERIAN,
            "transunion": cls.TRANSUNION,
            "isoftpull": cls.ISOFTPULL,
            "softpull": cls.ISOFTPULL,
        }
        if normalised not in mapping:
            raise ValueError(
                f"Unknown bureau '{value}'. "
                f"Expected one of: {list(mapping.keys())}"
            )
        return mapping[normalised]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class CreditBureauFactory:
    """
    Factory for credit bureau API clients.

    Manages one client instance per bureau (singleton pattern within a
    factory instance).  Clients are lazily initialised on first access.
    """

    def __init__(
        self,
        configs: Dict[Bureau, Dict[str, Any]],
    ) -> None:
        """
        Args:
            configs: Map of Bureau → client config dict.
                     Keys must be ``Bureau`` enum members.
                     Config dicts are forwarded verbatim to each client's
                     constructor.
        """
        self._configs = configs
        self._clients: Dict[Bureau, BaseBureauClient] = {}

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "CreditBureauFactory":
        """
        Create a factory with all clients configured from environment
        variables.

        Each client's ``from_env()`` class method handles its own env vars.
        See individual client modules for the full list.
        """
        # We use a sentinel config to signal "build from env"
        return cls(configs={})

    @classmethod
    def from_configs(cls, configs: Dict[Bureau, Dict[str, Any]]) -> "CreditBureauFactory":
        """
        Create a factory with explicit per-bureau config dicts.

        Useful for testing or when configs come from a secrets manager.

        Example::

            factory = CreditBureauFactory.from_configs({
                Bureau.EQUIFAX: {
                    "client_id": "...",
                    "client_secret": "...",
                    "org_id": "...",
                    "base_url": "https://api.equifax.com/...",
                    "token_url": "https://api.equifax.com/...",
                },
                Bureau.EXPERIAN: {...},
                Bureau.TRANSUNION: {...},
                Bureau.ISOFTPULL: {...},
            })
        """
        return cls(configs=configs)

    # ------------------------------------------------------------------
    # Client access
    # ------------------------------------------------------------------

    def get_client(self, bureau: Bureau) -> BaseBureauClient:
        """
        Return the (lazily constructed) client for the specified bureau.

        Args:
            bureau: ``Bureau`` enum member.

        Returns:
            The appropriate BaseBureauClient subclass instance.

        Raises:
            ValueError:        if the bureau is unknown.
            KeyError:          if no config was provided for this bureau
                               and the client cannot be built from env.
        """
        if bureau not in self._clients:
            self._clients[bureau] = self._build_client(bureau)
        return self._clients[bureau]

    def get_client_by_name(self, name: str) -> BaseBureauClient:
        """Convenience method: look up a client by bureau name string."""
        return self.get_client(Bureau.from_string(name))

    def _build_client(self, bureau: Bureau) -> BaseBureauClient:
        """Construct a new client instance for the given bureau."""
        if bureau == Bureau.EQUIFAX:
            if bureau in self._configs:
                return EquifaxClient(self._configs[bureau])
            return EquifaxClient.from_env()

        if bureau == Bureau.EXPERIAN:
            if bureau in self._configs:
                return ExperianClient(self._configs[bureau])
            return ExperianClient.from_env()

        if bureau == Bureau.TRANSUNION:
            if bureau in self._configs:
                return TransUnionClient(self._configs[bureau])
            return TransUnionClient.from_env()

        if bureau == Bureau.ISOFTPULL:
            if bureau in self._configs:
                return iSoftPullClient(self._configs[bureau])
            return iSoftPullClient.from_env()

        raise ValueError(f"Unsupported bureau: {bureau}")

    # ------------------------------------------------------------------
    # High-level operations
    # ------------------------------------------------------------------

    def pull_report(
        self,
        bureau: Bureau,
        client_id: str,
        consumer: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Pull a credit report from the specified bureau.

        Args:
            bureau:    Target bureau.
            client_id: Life Shield client ID.
            consumer:  Consumer PII dict.

        Returns:
            Normalised report dict (see individual client docstrings).
        """
        return self.get_client(bureau).pull_credit_report(client_id, consumer)

    def pull_all_reports(
        self,
        client_id: str,
        consumer: Dict[str, Any],
        bureaus: Optional[list[Bureau]] = None,
        max_workers: int = 3,
    ) -> Dict[str, Any]:
        """
        Pull credit reports from multiple bureaus concurrently.

        Args:
            client_id:   Life Shield client ID.
            consumer:    Consumer PII dict.
            bureaus:     List of bureaus to pull (default: all 3 main bureaus).
            max_workers: Thread pool size (default 3 — one per bureau).

        Returns:
            Dict keyed by bureau name string, value is the report dict or
            an error dict ``{"error": str}`` if that bureau failed.

        Example::

            reports = factory.pull_all_reports(
                client_id="ls-client-001",
                consumer={...},
            )
            equifax_score = reports["equifax"]["score"]
            experian_score = reports["experian"]["score"]
        """
        if bureaus is None:
            bureaus = [Bureau.EQUIFAX, Bureau.EXPERIAN, Bureau.TRANSUNION]

        results: Dict[str, Any] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_bureau = {
                executor.submit(
                    self.get_client(bureau).pull_credit_report, client_id, consumer
                ): bureau
                for bureau in bureaus
            }
            for future in as_completed(future_to_bureau):
                bureau = future_to_bureau[future]
                try:
                    results[bureau.value] = future.result()
                except CreditBureauError as exc:
                    logger.error(
                        "Failed to pull report from %s for client %s: %s",
                        bureau.value, client_id, exc,
                    )
                    results[bureau.value] = {"error": str(exc), "bureau": bureau.value}

        return results

    def file_dispute(
        self,
        bureau: Bureau,
        client_id: str,
        consumer: Dict[str, Any],
        item_id: str,
        reason: str,
        statement: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        File a dispute with the specified bureau.

        Args:
            bureau:     Target bureau.
            client_id:  Life Shield client ID.
            consumer:   Consumer PII dict.
            item_id:    Item identifier to dispute.
            reason:     Dispute reason code or description.
            statement:  Optional consumer statement.

        Returns:
            Dispute confirmation dict (see individual client docstrings).
        """
        return self.get_client(bureau).file_dispute(
            client_id, consumer, item_id, reason, statement
        )

    def file_dispute_all_bureaus(
        self,
        client_id: str,
        consumer: Dict[str, Any],
        disputes: list[Dict[str, Any]],
        max_workers: int = 3,
    ) -> Dict[str, Any]:
        """
        File disputes with multiple bureaus concurrently.

        Args:
            client_id: Life Shield client ID.
            consumer:  Consumer PII dict.
            disputes:  List of dicts, each with keys:
                       bureau (Bureau or str), item_id, reason, statement (opt)
            max_workers: Thread pool size.

        Returns:
            Dict keyed by "bureau:item_id" with result or error.
        """
        results: Dict[str, Any] = {}

        def _file(d: Dict[str, Any]) -> tuple[str, Any]:
            bureau = d["bureau"] if isinstance(d["bureau"], Bureau) else Bureau.from_string(d["bureau"])
            key = f"{bureau.value}:{d['item_id']}"
            try:
                result = self.get_client(bureau).file_dispute(
                    client_id,
                    consumer,
                    d["item_id"],
                    d["reason"],
                    d.get("statement"),
                )
                return key, result
            except CreditBureauError as exc:
                logger.error("Dispute filing failed for %s: %s", key, exc)
                return key, {"error": str(exc)}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_file, d) for d in disputes]
            for future in as_completed(futures):
                key, result = future.result()
                results[key] = result

        return results

    def get_dispute_status(
        self,
        bureau: Bureau,
        client_id: str,
        case_number: str,
        ssn: str,
    ) -> Dict[str, Any]:
        """
        Check the status of a dispute at the specified bureau.

        Args:
            bureau:      Target bureau.
            client_id:   Life Shield client ID.
            case_number: Case / confirmation number from file_dispute().
            ssn:         Consumer SSN.

        Returns:
            Dispute status dict (see individual client docstrings).
        """
        return self.get_client(bureau).get_dispute_status(
            client_id, case_number, ssn
        )

    def monitor_changes(
        self,
        bureau: Bureau,
        client_id: str,
        ssn: str,
        monitoring_type: str = "daily",
    ) -> Dict[str, Any]:
        """
        Poll a bureau for recent credit file changes.

        Args:
            bureau:          Target bureau.
            client_id:       Life Shield client ID.
            ssn:             Consumer SSN.
            monitoring_type: "daily" or "realtime".

        Returns:
            Changes dict (see individual client docstrings).
        """
        return self.get_client(bureau).monitor_changes(
            client_id, ssn, monitoring_type
        )

    def health_check_all(self) -> Dict[str, bool]:
        """
        Run health checks against all four providers concurrently.

        Returns:
            Dict keyed by bureau name string, value is True/False.

        Example::

            status = factory.health_check_all()
            # {"equifax": True, "experian": True, "transunion": True, "isoftpull": True}
        """
        all_bureaus = [
            Bureau.EQUIFAX, Bureau.EXPERIAN, Bureau.TRANSUNION, Bureau.ISOFTPULL
        ]
        results: Dict[str, bool] = {}

        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_bureau = {
                executor.submit(self.get_client(b).health_check): b
                for b in all_bureaus
            }
            for future in as_completed(future_to_bureau):
                bureau = future_to_bureau[future]
                try:
                    results[bureau.value] = future.result()
                except Exception as exc:  # noqa: BLE001
                    logger.error("Health check failed for %s: %s", bureau.value, exc)
                    results[bureau.value] = False

        return results
