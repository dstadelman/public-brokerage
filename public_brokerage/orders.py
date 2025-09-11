"""
Order management functions for the Public Brokerage API.
"""

from .client import PublicBrokerageClient
from .auth import ensure_access_token
from .models.order import (
    OrderRequest, MultiLegOrderRequest, OrderResponse,
    Order, PreflightResponse, MultiLegPreflightResponse
)


def preflight_single_leg(
    client: PublicBrokerageClient,
    account_id: str,
    order_request: OrderRequest
) -> PreflightResponse:
    """
    Calculate estimated financial impact of a single-leg order before execution.
    
    Args:
        client: Authenticated client instance
        account_id: Account ID for the order
        order_request: Order details for preflight calculation
        
    Returns:
        PreflightResponse with cost estimates and impact details
        
    Raises:
        requests.exceptions.RequestException: For HTTP errors
    """
    # Ensure we have a valid access token
    ensure_access_token(client)
    
    # Make the API request
    response = client._make_request(
        method="POST",
        endpoint=f"/userapigateway/trading/{account_id}/preflight/single-leg",
        data=order_request.model_dump()
    )
    
    # Parse response
    return client._handle_response(response, PreflightResponse)


def preflight_multi_leg(
    client: PublicBrokerageClient,
    account_id: str,
    order_request: MultiLegOrderRequest
) -> MultiLegPreflightResponse:
    """
    Calculate estimated financial impact of a multi-leg order before execution.
    
    Args:
        client: Authenticated client instance
        account_id: Account ID for the order
        order_request: Multi-leg order details for preflight calculation
        
    Returns:
        MultiLegPreflightResponse with cost estimates and impact details
        
    Raises:
        requests.exceptions.RequestException: For HTTP errors
    """
    # Ensure we have a valid access token
    ensure_access_token(client)
    
    # Make the API request
    response = client._make_request(
        method="POST",
        endpoint=f"/userapigateway/trading/{account_id}/preflight/multi-leg",
        data=order_request.model_dump()
    )
    
    # Parse response
    return client._handle_response(response, MultiLegPreflightResponse)


def place_order(
    client: PublicBrokerageClient,
    account_id: str,
    order_request: OrderRequest
) -> str:
    """
    Place a new single-leg order.
    
    Args:
        client: Authenticated client instance
        account_id: Account ID for the order
        order_request: Order details
        
    Returns:
        Order ID string
        
    Raises:
        requests.exceptions.RequestException: For HTTP errors
    """
    # Ensure we have a valid access token
    ensure_access_token(client)
    
    # Make the API request
    response = client._make_request(
        method="POST",
        endpoint=f"/userapigateway/trading/{account_id}/order",
        data=order_request.model_dump()
    )
    
    # Parse response
    order_response = client._handle_response(response, OrderResponse)
    return order_response.orderId


def place_multileg_order(
    client: PublicBrokerageClient,
    account_id: str,
    order_request: MultiLegOrderRequest
) -> str:
    """
    Place a new multi-leg order.
    
    Args:
        client: Authenticated client instance
        account_id: Account ID for the order
        order_request: Multi-leg order details
        
    Returns:
        Order ID string
        
    Raises:
        requests.exceptions.RequestException: For HTTP errors
    """
    # Ensure we have a valid access token
    ensure_access_token(client)
    
    # Make the API request
    response = client._make_request(
        method="POST",
        endpoint=f"/userapigateway/trading/{account_id}/order/multileg",
        data=order_request.model_dump()
    )
    
    # Parse response
    order_response = client._handle_response(response, OrderResponse)
    return order_response.orderId


def get_order(
    client: PublicBrokerageClient,
    account_id: str,
    order_id: str
) -> Order:
    """
    Get details for a specific order.
    
    Args:
        client: Authenticated client instance
        account_id: Account ID for the order
        order_id: Order ID to retrieve
        
    Returns:
        Order object with details and status
        
    Raises:
        requests.exceptions.RequestException: For HTTP errors
    """
    # Ensure we have a valid access token
    ensure_access_token(client)
    
    # Make the API request
    response = client._make_request(
        method="GET",
        endpoint=f"/userapigateway/trading/{account_id}/order/{order_id}"
    )
    
    # Parse response
    return client._handle_response(response, Order)


def cancel_order(
    client: PublicBrokerageClient,
    account_id: str,
    order_id: str
) -> None:
    """
    Request cancellation of a specific order.
    
    Args:
        client: Authenticated client instance
        account_id: Account ID for the order
        order_id: Order ID to cancel
        
    Returns:
        None (cancellation request submitted)
        
    Raises:
        requests.exceptions.RequestException: For HTTP errors
    """
    # Ensure we have a valid access token
    ensure_access_token(client)
    
    # Make the API request
    response = client._make_request(
        method="DELETE",
        endpoint=f"/userapigateway/trading/{account_id}/order/{order_id}"
    )
    
    # Cancel order returns 200 with no response body, just check status
    if response.status_code != 200:
        raise Exception(f"Cancel order failed with status {response.status_code}")
    
    # Success - no need to parse empty response body
