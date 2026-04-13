"""
Credit Bureau Client Factory - Creates appropriate bureau clients based on config
Supports: Equifax, Experian, TransUnion, iSoftPull
"""

import os
from typing import Dict, Optional
from .equifax import EquifaxClient
from .experian import ExperianClient
from .transunion import TransUnionClient
from .isoftpull import iSoftPullClient

def get_bureau_clients() -> Dict[str, object]:
    """
    Get all configured bureau clients
    Returns dict like: {
        'equifax': EquifaxClient(...),
        'experian': ExperianClient(...),
        'transunion': TransUnionClient(...),
        'isoftpull': iSoftPullClient(...)
    }
    """
    clients = {}
    
    # Equifax
    equifax_api_key = os.getenv("EQUIFAX_API_KEY")
    equifax_api_secret = os.getenv("EQUIFAX_API_SECRET")
    if equifax_api_key and equifax_api_secret:
        clients['equifax'] = EquifaxClient(
            api_key=equifax_api_key,
            api_secret=equifax_api_secret,
            api_url=os.getenv("EQUIFAX_API_URL", "https://api.equifax.com")
        )
    
    # Experian
    experian_api_key = os.getenv("EXPERIAN_API_KEY")
    experian_api_secret = os.getenv("EXPERIAN_API_SECRET")
    if experian_api_key and experian_api_secret:
        clients['experian'] = ExperianClient(
            api_key=experian_api_key,
            api_secret=experian_api_secret,
            api_url=os.getenv("EXPERIAN_API_URL", "https://api.experian.com")
        )
    
    # TransUnion
    transunion_api_key = os.getenv("TRANSUNION_API_KEY")
    transunion_api_secret = os.getenv("TRANSUNION_API_SECRET")
    if transunion_api_key and transunion_api_secret:
        clients['transunion'] = TransUnionClient(
            api_key=transunion_api_key,
            api_secret=transunion_api_secret,
            api_url=os.getenv("TRANSUNION_API_URL", "https://api.transunion.com")
        )
    
    # iSoftPull
    isoftpull_api_key = os.getenv("ISOFTPULL_API_KEY")
    if isoftpull_api_key:
        clients['isoftpull'] = iSoftPullClient(
            api_key=isoftpull_api_key,
            api_url=os.getenv("ISOFTPULL_API_URL", "https://api.isoftpull.com")
        )
    
    return clients

def get_bureau_client(bureau: str) -> Optional[object]:
    """
    Get specific bureau client by name
    Returns client or None if not configured
    """
    clients = get_bureau_clients()
    return clients.get(bureau.lower())

def get_available_bureaus() -> list:
    """Get list of available (configured) bureaus"""
    return list(get_bureau_clients().keys())
