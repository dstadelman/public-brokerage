"""
Order management functions for the Public Brokerage API.
"""

import time
import logging
import threading
from concurrent.futures import Future
from typing import Optional

from .client import PublicBrokerageClient
from .auth import ensure_access_token
from .models.order import (
    OrderRequest, MultiLegOrderRequest, OrderResponse,
    Order, PreflightResponse, MultiLegPreflightResponse,
    SingleLegPreflightRequest
)
from .models.order_state import OrderState

# Import worker pool and API queue
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from worker_pool import submit_task, is_task_cancelled
from api_queue import queue_http_request

logger = logging.getLogger(__name__)


# ============================================================================
# Error Classes
# ============================================================================

class OrderPlacementError(Exception):
    """Base exception for order placement errors."""
    pass


class OrderVerificationError(OrderPlacementError):
    """Error during order status verification."""
    pass


class OrderCancelledException(OrderPlacementError):
    """Order operation was cancelled."""
    def __init__(self, message: str = "Order operation cancelled", partial_result: Optional[Order] = None):
        super().__init__(message)
        self.partial_result = partial_result


class OrderTimeoutError(OrderPlacementError):
    """Order operation timed out."""
    pass


class OrderApiError(OrderPlacementError):
    """API returned an error response."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


# ============================================================================
# Original Functions (preserved for backward compatibility)
# ============================================================================


def preflight_single_leg(
    client: PublicBrokerageClient,
    account_id: str,
    preflight_request: SingleLegPreflightRequest
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
        data=preflight_request.model_dump()
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


def place_single_leg_order(
    client: PublicBrokerageClient,
    account_id: str,
    order_request: OrderRequest
) -> OrderResponse:
    """
    Place a new single-leg order (alias for place_order with OrderResponse return).
    
    Args:
        client: Authenticated client instance
        account_id: Account ID for the order
        order_request: Order details
        
    Returns:
        OrderResponse object
        
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
    
    # Parse response and return full OrderResponse object
    return client._handle_response(response, OrderResponse)


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


# ============================================================================
# WORKER-BASED ORDER PLACEMENT (THREE-THREAD ARCHITECTURE)
# ============================================================================


def _execute_order_placement_worker(
    task_id: str,
    client: PublicBrokerageClient,
    account_id: str,
    order_request: MultiLegOrderRequest,
    auth_token: str
) -> str:
    """
    Internal worker function to place a multi-leg order.
    
    Runs in worker thread. Calls queue_http_request() which executes in API thread.
    
    Args:
        task_id: Unique task ID (used for cancellation checks)
        client: Client instance (for base URL)
        account_id: Account ID for the order
        order_request: Multi-leg order details
        auth_token: Bearer token for authentication
        
    Returns:
        Order ID string
        
    Raises:
        OrderCancelledException: If cancelled before placement
        OrderApiError: If API returns an error
        Exception: If order placement fails
    """
    # Check for cancellation before starting
    if is_task_cancelled(task_id):
        raise OrderCancelledException("Order placement cancelled before execution")
    
    logger.info(f"[WORKER] Placing multi-leg order for account {account_id}")
    
    try:
        # Place order via API thread
        response = queue_http_request(
            method="POST",
            endpoint=f"/userapigateway/trading/{account_id}/order/multileg",
            data=order_request.model_dump(),
            auth_token=auth_token,
            base_url_override=client.base_url
        )
        
        # Check response status
        if response.status_code >= 400:
            error_data = None
            try:
                error_data = response.json()
            except:
                pass
            
            raise OrderApiError(
                f"Order placement failed with status {response.status_code}",
                status_code=response.status_code,
                response_data=error_data
            )
        
        # Parse response
        response_data = response.json()
        order_id = response_data.get("orderId")
        
        if not order_id:
            raise OrderPlacementError(f"No orderId in response: {response_data}")
        
        logger.info(f"[WORKER] Order placed successfully: {order_id}")
        return order_id
        
    except OrderCancelledException:
        raise
    except OrderApiError:
        raise
    except Exception as e:
        logger.error(f"[WORKER] Order placement failed: {e}")
        raise OrderPlacementError(f"Failed to place order: {e}") from e


def _verify_order_status_worker(
    task_id: str,
    client: PublicBrokerageClient,
    account_id: str,
    order_id: str,
    auth_token: str,
    max_checks: int = 10,
    check_interval: float = 1.0
) -> Order:
    """
    Internal worker function to verify order status with polling.
    
    Runs in worker thread. Implements verification loop with proper timing:
    - Wait 1 second before first check
    - Poll up to max_checks times
    - Wait check_interval between checks
    - Wait 1 additional second after order updates
    
    Args:
        task_id: Unique task ID (used for cancellation checks)
        client: Client instance (for base URL)
        account_id: Account ID for the order
        order_id: Order ID to verify
        auth_token: Bearer token for authentication
        max_checks: Maximum number of status checks (default: 10)
        check_interval: Seconds between checks (default: 1.0)
        
    Returns:
        Final Order object with updated status
        
    Raises:
        OrderCancelledException: If cancelled during verification (includes partial result)
        OrderVerificationError: If verification fails
        OrderApiError: If API returns an error
        OrderTimeoutError: If max checks exceeded
    """
    logger.info(f"[WORKER] Starting verification for order {order_id}")
    
    # Step 1: Wait 1 second before first check (check for cancellation during wait)
    logger.debug(f"[WORKER] Waiting {check_interval}s before first status check")
    # Sleep in small increments to check for cancellation
    elapsed = 0.0
    increment = 0.1
    while elapsed < check_interval:
        if is_task_cancelled(task_id):
            raise OrderCancelledException(
                f"Verification cancelled before first check (order {order_id} placed)",
                partial_result=None
            )
        time.sleep(min(increment, check_interval - elapsed))
        elapsed += increment
    
    last_order = None
    
    # Step 2: Poll order status
    for attempt in range(max_checks):
        # Check for cancellation before each attempt
        if is_task_cancelled(task_id):
            raise OrderCancelledException(
                f"Verification cancelled at attempt {attempt + 1} of {max_checks}",
                partial_result=last_order
            )
        
        logger.debug(f"[WORKER] Status check attempt {attempt + 1}/{max_checks}")
        
        try:
            # Get order status via API thread
            response = queue_http_request(
                method="GET",
                endpoint=f"/userapigateway/trading/{account_id}/order/{order_id}",
                auth_token=auth_token,
                base_url_override=client.base_url
            )
            
            # Check response status
            if response.status_code >= 400:
                error_data = None
                try:
                    error_data = response.json()
                except:
                    pass
                
                raise OrderApiError(
                    f"Order status check failed with status {response.status_code}",
                    status_code=response.status_code,
                    response_data=error_data
                )
            
            # Parse order
            order_data = response.json()
            order = Order.model_validate(order_data)
            last_order = order
            
            # Check if order status has updated
            order_status = OrderState(order.status)
            logger.debug(f"[WORKER] Order status: {order_status.value}")
            
            # If order is no longer NEW, it has been updated
            if order_status != OrderState.NEW:
                logger.info(f"[WORKER] Order updated to status: {order_status.value}")
                
                # Step 3: Wait 1 additional second after update (check for cancellation)
                logger.debug(f"[WORKER] Waiting {check_interval}s after order update")
                elapsed = 0.0
                increment = 0.1
                while elapsed < check_interval:
                    if is_task_cancelled(task_id):
                        # Return order even if cancelled during final wait
                        logger.info(f"[WORKER] Cancelled during final wait, returning order")
                        return order
                    time.sleep(min(increment, check_interval - elapsed))
                    elapsed += increment
                
                return order
            
        except OrderCancelledException:
            raise
        except OrderApiError:
            raise
        except Exception as e:
            logger.error(f"[WORKER] Error checking order status: {e}")
            raise OrderVerificationError(f"Failed to verify order {order_id}: {e}") from e
        
        # Order still NEW, wait before next check (unless it's the last attempt)
        if attempt < max_checks - 1:
            logger.debug(f"[WORKER] Order still NEW, waiting {check_interval}s before next check")
            
            # Sleep with cancellation checks
            elapsed = 0.0
            increment = 0.1
            while elapsed < check_interval:
                if is_task_cancelled(task_id):
                    raise OrderCancelledException(
                        f"Verification cancelled during wait (attempt {attempt + 1})",
                        partial_result=last_order
                    )
                time.sleep(min(increment, check_interval - elapsed))
                elapsed += increment
    
    # Max checks exceeded
    logger.warning(f"[WORKER] Order {order_id} still in NEW status after {max_checks} checks")
    raise OrderTimeoutError(
        f"Order {order_id} verification timed out after {max_checks} checks ({max_checks * check_interval}s)"
    )


def place_multileg_order_with_verification_worker(
    client: PublicBrokerageClient,
    account_id: str,
    order_request: MultiLegOrderRequest
) -> tuple[str, Future[Order]]:
    """
    Place a multi-leg order with verification (WORKER-BASED, NON-BLOCKING).
    
    This function submits the order placement to a worker thread and returns
    immediately with a tuple of (task_id, Future). The main thread stays responsive.
    
    The worker thread:
    1. Places the order (via queue_http_request)
    2. Waits 1 second
    3. Checks order status
    4. Loops if status is still NEW (max 10 checks, 1s between checks)
    5. Waits 1 additional second after order updates
    6. Returns final Order object
    
    All API calls go through queue_http_request() which executes in API thread.
    All timing/delays happen in worker thread (NOT in API thread).
    
    The task can be cancelled by calling: `cancel_task(task_id)` from worker_pool module.
    
    Args:
        client: Authenticated client instance
        account_id: Account ID for the order
        order_request: Multi-leg order details
        
    Returns:
        Tuple of (task_id, Future[Order])
        - task_id: Use this to cancel the task via cancel_task(task_id)
        - Future: Call .result() to block and get final order
        
    Raises:
        OrderPlacementError: If order placement fails
        OrderVerificationError: If verification fails  
        OrderApiError: If API returns an error
        OrderTimeoutError: If verification times out
        OrderCancelledException: If cancelled via cancel_task(task_id)
        
    Example:
        # Non-blocking (async)
        task_id, future = place_multileg_order_with_verification_worker(
            client, account_id, order_request
        )
        # Do other work...
        order = future.result()  # Block and wait for result
        
        # With cancellation support
        task_id, future = place_multileg_order_with_verification_worker(
            client, account_id, order_request
        )
        # ... later, cancel if needed ...
        from worker_pool import cancel_task
        cancel_task(task_id)
        try:
            order = future.result()
        except OrderCancelledException as e:
            print(f"Cancelled: {e}")
            if e.partial_result:
                print(f"Partial order: {e.partial_result}")
    """
    # Ensure we have a valid access token
    ensure_access_token(client)
    auth_token = client.get_access_token()
    
    if not auth_token:
        raise Exception("No valid access token available")
    
    def _worker_task(task_id: str):
        """Worker task that runs in worker thread. Receives task_id as first parameter."""
        # Step 1: Place order
        order_id = _execute_order_placement_worker(
            task_id=task_id,
            client=client,
            account_id=account_id,
            order_request=order_request,
            auth_token=auth_token
        )
        
        # Step 2: Verify order status with polling
        order = _verify_order_status_worker(
            task_id=task_id,
            client=client,
            account_id=account_id,
            order_id=order_id,
            auth_token=auth_token
        )
        
        return order
    
    # Submit to worker pool (non-blocking)
    logger.info(f"[MAIN] Submitting order placement to worker thread")
    task_id, worker_thread = submit_task(_worker_task, f"place-order-{account_id}")
    
    # Create a Future-like wrapper for compatibility
    from concurrent.futures import Future as ConcurrentFuture
    future = ConcurrentFuture()
    
    def _complete_future():
        """Wait for worker and complete the future."""
        worker_thread.join()
        if worker_thread.error:
            future.set_exception(worker_thread.error)
        else:
            future.set_result(worker_thread.result)
    
    # Start a daemon thread to complete the future when worker finishes
    import threading
    completion_thread = threading.Thread(target=_complete_future, daemon=True)
    completion_thread.start()
    
    return task_id, future


def place_multileg_order_with_verification(
    client: PublicBrokerageClient,
    account_id: str,
    order_request: MultiLegOrderRequest
) -> Order:
    """
    Place a multi-leg order with verification (BLOCKING, backward compatible).
    
    This is a blocking wrapper around place_multileg_order_with_verification_worker()
    that maintains the synchronous interface for backward compatibility.
    
    For non-blocking operation, use place_multileg_order_with_verification_worker()
    which returns (task_id, future) allowing cancellation and async behavior.
    
    Args:
        client: Authenticated client instance
        account_id: Account ID for the order
        order_request: Multi-leg order details
        
    Returns:
        Order object with final status
    """
    logger.info("[MAIN] Placing order with verification (blocking)")
    task_id, future = place_multileg_order_with_verification_worker(client, account_id, order_request)
    return future.result()  # Block and wait for worker to complete
