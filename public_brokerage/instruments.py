"""
Instrument functions for the Public Brokerage API.
"""

from typing import List, Optional

from .client import PublicBrokerageClient
from .auth import ensure_access_token
from .models.instrument import InstrumentWithTrading, InstrumentsResponse


def get_all_instruments(
    client: PublicBrokerageClient,
    type_filter: Optional[List[str]] = None,
    trading_filter: Optional[List[str]] = None,
    fractional_trading_filter: Optional[List[str]] = None,
    option_trading_filter: Optional[List[str]] = None,
    option_spread_trading_filter: Optional[List[str]] = None
) -> List[InstrumentWithTrading]:
    """
    Get all available trading instruments with optional filtering.
    
    Args:
        client: Authenticated client instance
        type_filter: Optional set of security types to filter by
        trading_filter: Optional set of trading statuses to filter by
        fractional_trading_filter: Optional set of fractional trading statuses
        option_trading_filter: Optional set of option trading statuses
        option_spread_trading_filter: Optional set of option spread trading statuses
        
    Returns:
        List of InstrumentWithTrading objects
        
    Raises:
        requests.exceptions.RequestException: For HTTP errors
    """
    # Ensure we have a valid access token
    ensure_access_token(client)
    
    # Build query parameters
    params = {}
    if type_filter:
        params["typeFilter"] = type_filter
    if trading_filter:
        params["tradingFilter"] = trading_filter
    if fractional_trading_filter:
        params["fractionalTradingFilter"] = fractional_trading_filter
    if option_trading_filter:
        params["optionTradingFilter"] = option_trading_filter
    if option_spread_trading_filter:
        params["optionSpreadTradingFilter"] = option_spread_trading_filter
    
    # Make the API request
    response = client._make_request(
        method="GET",
        endpoint="/userapigateway/trading/instruments",
        params=params if params else None
    )
    
    # Parse response
    instruments_response = client._handle_response(response, InstrumentsResponse)
    return instruments_response.instruments


def get_instrument(
    client: PublicBrokerageClient,
    symbol: str,
    instrument_type: str
) -> InstrumentWithTrading:
    """
    Get details for a specific instrument.
    
    Args:
        client: Authenticated client instance
        symbol: Instrument symbol
        instrument_type: Instrument type (e.g., "EQUITY", "OPTION")
        
    Returns:
        InstrumentWithTrading object
        
    Raises:
        requests.exceptions.RequestException: For HTTP errors
    """
    # Ensure we have a valid access token
    ensure_access_token(client)
    
    # Make the API request
    response = client._make_request(
        method="GET",
        endpoint=f"/userapigateway/trading/instruments/{symbol}/{instrument_type}"
    )
    
    # Parse response
    return client._handle_response(response, InstrumentWithTrading)
