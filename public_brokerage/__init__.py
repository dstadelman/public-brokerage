"""
Public Brokerage API Python Library

A Python library for executing trades on Public brokerage using their API.
Supports all endpoints including authentication, account management, market data,
and order placement.
"""

# Import main classes and functions when available
try:
    from .client import PublicBrokerageClient
    from .auth import create_access_token
    from .accounts import get_accounts, get_account_portfolio, get_account_history
    from .instruments import get_all_instruments, get_instrument
    from .market_data import (
        get_quotes,
        get_option_expirations,
        get_option_chain,
        get_option_greeks
    )
    from .orders import (
        preflight_single_leg,
        preflight_multi_leg,
        place_order,
        place_multileg_order,
        get_order,
        cancel_order
    )
except ImportError:
    # Handle case where dependencies aren't installed yet
    pass

__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

__all__ = [
    "PublicBrokerageClient",
    "create_access_token",
    "get_accounts",
    "get_account_portfolio", 
    "get_account_history",
    "get_all_instruments",
    "get_instrument",
    "get_quotes",
    "get_option_expirations",
    "get_option_chain",
    "get_option_greeks",
    "preflight_single_leg",
    "preflight_multi_leg",
    "place_order",
    "place_multileg_order",
    "get_order",
    "cancel_order",
]
