"""
Market data functions for the Public Brokerage API.
"""

from typing import List
from datetime import date

from .client import PublicBrokerageClient
from .auth import ensure_access_token
from .models.common import Instrument
from .models.market_data import (
    QuotesRequest, QuotesResponse, Quote,
    OptionExpirationsRequest, OptionExpirationsResponse,
    OptionChainRequest, OptionChainResponse,
    OptionGreeks
)


def get_quotes(
    client: PublicBrokerageClient,
    account_id: str,
    instruments: List[Instrument]
) -> List[Quote]:
    """
    Get real-time quotes for a list of instruments.
    
    Args:
        client: Authenticated client instance
        account_id: Account ID for the request
        instruments: List of instruments to get quotes for
        
    Returns:
        List of Quote objects
        
    Raises:
        requests.exceptions.RequestException: For HTTP errors
    """
    # Ensure we have a valid access token
    ensure_access_token(client)
    
    # Create request payload
    request_data = QuotesRequest(instruments=instruments)
    
    # Make the API request
    response = client._make_request(
        method="POST",
        endpoint=f"/userapigateway/marketdata/{account_id}/quotes",
        data=request_data.model_dump()
    )
    
    # Parse response
    quotes_response = client._handle_response(response, QuotesResponse)
    return quotes_response.quotes


def get_option_expirations(
    client: PublicBrokerageClient,
    account_id: str,
    instrument: Instrument
) -> List[date]:
    """
    Get available option expiration dates for an instrument.
    
    Args:
        client: Authenticated client instance
        account_id: Account ID for the request
        instrument: Instrument to get expirations for
        
    Returns:
        List of expiration dates
        
    Raises:
        requests.exceptions.RequestException: For HTTP errors
    """
    # Ensure we have a valid access token
    ensure_access_token(client)
    
    # Create request payload
    request_data = OptionExpirationsRequest(instrument=instrument)
    
    # Make the API request
    response = client._make_request(
        method="POST",
        endpoint=f"/userapigateway/marketdata/{account_id}/option-expirations",
        data=request_data.model_dump()
    )
    
    # Parse response
    expirations_response = client._handle_response(response, OptionExpirationsResponse)
    return expirations_response.expirations


def get_option_chain(
    client: PublicBrokerageClient,
    account_id: str,
    instrument: Instrument,
    expiration_date: date
) -> OptionChainResponse:
    """
    Get option chain for an instrument and expiration date.
    
    Args:
        client: Authenticated client instance
        account_id: Account ID for the request
        instrument: Underlying instrument
        expiration_date: Option expiration date
        
    Returns:
        OptionChainResponse with calls and puts
        
    Raises:
        requests.exceptions.RequestException: For HTTP errors
    """
    # Ensure we have a valid access token
    ensure_access_token(client)
    
    # Create request payload
    request_data = OptionChainRequest(
        instrument=instrument,
        expirationDate=expiration_date
    )
    
    # Make the API request
    response = client._make_request(
        method="POST",
        endpoint=f"/userapigateway/marketdata/{account_id}/option-chain",
        data=request_data.model_dump(mode='json')
    )
    
    # Parse response
    return client._handle_response(response, OptionChainResponse)


def get_option_greeks(
    client: PublicBrokerageClient,
    account_id: str,
    osi_option_symbol: str
) -> OptionGreeks:
    """
    Get option Greeks for a specific option symbol.
    
    Args:
        client: Authenticated client instance
        account_id: Account ID for the request
        osi_option_symbol: OSI-normalized option symbol
        
    Returns:
        OptionGreeks object
        
    Raises:
        requests.exceptions.RequestException: For HTTP errors
    """
    # Ensure we have a valid access token
    ensure_access_token(client)
    
    # Make the API request
    response = client._make_request(
        method="GET",
        endpoint=f"/userapigateway/option-details/{account_id}/{osi_option_symbol}/greeks"
    )
    
    # Parse response
    return client._handle_response(response, OptionGreeks)
