"""
Account management functions for the Public Brokerage API.
"""

from typing import List, Optional
from datetime import datetime

from .client import PublicBrokerageClient
from .auth import ensure_access_token
from .models.account import AccountsResponse, HistoryResponse
from .models.portfolio import Portfolio


def get_accounts(client: PublicBrokerageClient) -> List:
    """
    Get all accounts associated with the authenticated user.
    
    Args:
        client: Authenticated client instance
        
    Returns:
        List of Account objects
        
    Raises:
        requests.exceptions.RequestException: For HTTP errors
    """
    # Ensure we have a valid access token
    ensure_access_token(client)
    
    # Make the API request
    response = client._make_request(
        method="GET",
        endpoint="/userapigateway/trading/account"
    )
    
    # Parse response
    accounts_response = client._handle_response(response, AccountsResponse)
    return accounts_response.accounts


def get_account_portfolio(client: PublicBrokerageClient, account_id: str) -> Portfolio:
    """
    Get portfolio details for a specific account.
    
    Args:
        client: Authenticated client instance
        account_id: Account ID to get portfolio for
        
    Returns:
        Portfolio object with positions, equity, and orders
        
    Raises:
        requests.exceptions.RequestException: For HTTP errors
    """
    # Ensure we have a valid access token
    ensure_access_token(client)
    
    # Make the API request
    response = client._make_request(
        method="GET",
        endpoint=f"/userapigateway/trading/{account_id}/portfolio/v2"
    )
    
    # Parse response
    return client._handle_response(response, Portfolio)


def get_account_history(
    client: PublicBrokerageClient,
    account_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    page_size: Optional[int] = None,
    next_token: Optional[str] = None
) -> HistoryResponse:
    """
    Get historical transactions for a specific account.
    
    Args:
        client: Authenticated client instance
        account_id: Account ID to get history for
        start: Start timestamp (ISO 8601 format)
        end: End timestamp (ISO 8601 format)
        page_size: Maximum number of records to return
        next_token: Pagination token for next page
        
    Returns:
        HistoryResponse with transactions and pagination info
        
    Raises:
        requests.exceptions.RequestException: For HTTP errors
    """
    # Ensure we have a valid access token
    ensure_access_token(client)
    
    # Build query parameters
    params = {}
    if start:
        params["start"] = start.isoformat()
    if end:
        params["end"] = end.isoformat()
    if page_size:
        params["pageSize"] = page_size
    if next_token:
        params["nextToken"] = next_token
    
    # Make the API request
    response = client._make_request(
        method="GET",
        endpoint=f"/userapigateway/trading/{account_id}/history",
        params=params if params else None
    )
    
    # Parse response
    return client._handle_response(response, HistoryResponse)
