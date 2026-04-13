"""
Credit Bureau Client Factory — The Life Shield

Factory pattern for instantiating bureau clients by name or enum.

Usage::

    from api.credit_bureaus.client_factory import CreditBureauFactory, Bureau

    factory = CreditBureauFactory.from_env()

    equifax = factory.get_client(Bureau.EQUIFAX)
    report = factory.pull_report(Bureau.EQUIFAX, "ls-client-001", consumer={...})

    # Pull all 3 bureaus concurrently
    reports = factory.pull_all_reports("ls-client-001", consumer={...})

    # Health check all
    status = factory.health_check_all()
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
from typing import Any, Dict, List, Optional

from .base import BaseBureauClient, CreditBureauError
from .equifax import EquifaxClient
from .experian import ExperianClient
from .isoftpull import iSoftPullClient
from .transunion import TransUnionClient

logger = logging.getLogger(__name__)


class Bureau(str, Enum):
    """Canonical bureau identifiers."""

    EQUIFAX = "equifax"
    EXPERIAN = "experian"
    TRANSUNION = "transunion"
    ISOFTPULL = "isoftpull"

    @classmethod
    def from_string(cls, value: str) -> "Bureau":
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
                f"Unknown bureau '{value}'. Expected: {list(mapping.keys())}"
            )
        return mapping[normalised]


class CreditBureauFactory:
    """
    Factory for credit bureau API clients.

    Lazily initialises one client per bureau (singleton within factory).
    """

    def __init__(self, configs: Optional[Dict[Bureau, Dict[str, Any]]] = None) -> None:
        self._configs: Dict[Bureau, Dict[str, Any]] = configs or {}
        self._clients: Dict[Bureau, BaseBureauClient] = {}

    @classmethod
    def from_env(cls) -> "CreditBureauFactory":
        """Create factory with all clients configured from environment variables."""
        return cls(configs={})

    @classmethod
    def from_configs(cls, configs: Dict[Bureau, Dict[str, Any]]) -> "CreditBureauFactory":
        """Create factory with explicit per-bureau config dicts."""
        return cls(configs=configs)

    # ------------------------------------------------------------------
    # Client access
    # ------------------------------------------------------------------

    def get_client(self, bureau: Bureau) -> BaseBureauClient:
        """Return the (lazily-built) client for the specified bureau."""
        if bureau not in self._clients:
            self._clients[bureau] = self._build_client(bureau)
        return self._clients[bureau]

    def get_client_by_name(self, name: str) -> BaseBureauClient:
        """Look up a client by bureau name string."""
        return self.get_client(Bureau.from_string(name))

    def _build_client(self, bureau: Bureau) -> BaseBureauClient:
        builders = {
            Bureau.EQUIFAX: (EquifaxClient, EquifaxClient.from_env),
            Bureau.EXPERIAN: (ExperianClient, ExperianClient.from_env),
            Bureau.TRANSUNION: (TransUnionClient, TransUnionClient.from_env),
            Bureau.ISOFTPULL: (iSoftPullClient, iSoftPullClient.from_env),
        }
        if bureau not in builders:
            raise ValueError(f"Unsupported bureau: {bureau}")

        cls_type, env_factory = builders[bureau]
        if bureau in self._configs:
            return cls_type(self._configs[bureau])
        return env_factory()

    # ------------------------------------------------------------------
    # High-level operations
    # ------------------------------------------------------------------

    def pull_report(
        self, bureau: Bureau, client_id: str, consumer: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Pull a credit report from one bureau."""
        return self.get_client(bureau).pull_credit_report(client_id, consumer)

    def pull_all_reports(
        self,
        client_id: str,
        consumer: Dict[str, Any],
        bureaus: Optional[List[Bureau]] = None,
        max_workers: int = 3,
    ) -> Dict[str, Any]:
        """
        Pull credit reports from multiple bureaus concurrently.

        Returns dict keyed by bureau name, value is report or {"error": str}.
        """
        if bureaus is None:
            bureaus = [Bureau.EQUIFAX, Bureau.EXPERIAN, Bureau.TRANSUNION]

        results: Dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_bureau = {
                executor.submit(
                    self.get_client(b).pull_credit_report, client_id, consumer
                ): b
                for b in bureaus
            }
            for future in as_completed(future_to_bureau):
                bureau = future_to_bureau[future]
                try:
                    results[bureau.value] = future.result()
                except CreditBureauError as exc:
                    logger.error("Failed to pull %s for %s: %s", bureau.value, client_id, exc)
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
        """File a dispute with a specific bureau."""
        return self.get_client(bureau).file_dispute(
            client_id, consumer, item_id, reason, statement
        )

    def file_dispute_all_bureaus(
        self,
        client_id: str,
        consumer: Dict[str, Any],
        disputes: List[Dict[str, Any]],
        max_workers: int = 3,
    ) -> Dict[str, Any]:
        """
        File disputes with multiple bureaus concurrently.

        disputes: list of dicts with keys: bureau, item_id, reason, statement (opt).
        Returns dict keyed by "bureau:item_id".
        """
        results: Dict[str, Any] = {}

        def _file(d: Dict[str, Any]) -> tuple:
            bureau = d["bureau"] if isinstance(d["bureau"], Bureau) else Bureau.from_string(d["bureau"])
            key = f"{bureau.value}:{d['item_id']}"
            try:
                result = self.get_client(bureau).file_dispute(
                    client_id, consumer, d["item_id"], d["reason"], d.get("statement"),
                )
                return key, result
            except CreditBureauError as exc:
                logger.error("Dispute failed for %s: %s", key, exc)
                return key, {"error": str(exc)}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_file, d) for d in disputes]
            for future in as_completed(futures):
                key, result = future.result()
                results[key] = result

        return results

    def get_dispute_status(
        self, bureau: Bureau, client_id: str, case_number: str, ssn: str,
    ) -> Dict[str, Any]:
        """Check dispute status at a specific bureau."""
        return self.get_client(bureau).get_dispute_status(client_id, case_number, ssn)

    def monitor_changes(
        self, bureau: Bureau, client_id: str, ssn: str, monitoring_type: str = "daily",
    ) -> Dict[str, Any]:
        """Poll a bureau for recent credit file changes."""
        return self.get_client(bureau).monitor_changes(client_id, ssn, monitoring_type)

    def health_check_all(self) -> Dict[str, bool]:
        """
        Run health checks against all four providers concurrently.
        Returns dict keyed by bureau name, value is True/False.
        """
        all_bureaus = [Bureau.EQUIFAX, Bureau.EXPERIAN, Bureau.TRANSUNION, Bureau.ISOFTPULL]
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
                except Exception:
                    logger.error("Health check failed for %s", bureau.value, exc_info=True)
                    results[bureau.value] = False

        return results
