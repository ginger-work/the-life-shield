"""
Credit Bureau API Clients
The Life Shield - Phase 2

Provides Python clients for:
- Equifax (OAuth 2.0)
- Experian (OAuth 2.0)
- TransUnion (API Key + Secret)
- iSoftPull (soft pull monitoring)
- CreditBureauFactory (factory pattern)
"""

from .equifax import EquifaxClient
from .experian import ExperianClient
from .transunion import TransUnionClient
from .isoftpull import iSoftPullClient
from .client_factory import CreditBureauFactory, Bureau

__all__ = [
    "EquifaxClient",
    "ExperianClient",
    "TransUnionClient",
    "iSoftPullClient",
    "CreditBureauFactory",
    "Bureau",
]
