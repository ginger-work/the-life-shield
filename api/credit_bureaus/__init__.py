"""
Credit Bureau API Clients — The Life Shield Phase 2

Provides Python clients for:
- Equifax (OAuth 2.0)
- Experian (OAuth 2.0)
- TransUnion (HMAC API Key + Secret)
- iSoftPull (soft pull monitoring, API key)
- CreditBureauFactory (factory pattern for all bureaus)
"""

from .base import (
    AuthenticationError,
    BaseBureauClient,
    CreditBureauError,
    DisputeError,
    RateLimitError,
    ReportPullError,
    ValidationError,
)
from .client_factory import Bureau, CreditBureauFactory
from .equifax import EquifaxClient
from .experian import ExperianClient
from .isoftpull import iSoftPullClient
from .transunion import TransUnionClient

__all__ = [
    "AuthenticationError",
    "BaseBureauClient",
    "Bureau",
    "CreditBureauError",
    "CreditBureauFactory",
    "DisputeError",
    "EquifaxClient",
    "ExperianClient",
    "RateLimitError",
    "ReportPullError",
    "TransUnionClient",
    "ValidationError",
    "iSoftPullClient",
]
