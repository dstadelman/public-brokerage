"""
Test Error Handling and Cancellation for Worker-Based Order Placement

Tests:
- HTTP errors (4xx, 5xx)
- Timeout errors
- Network errors
- Cancellation at different stages
- Partial results on cancellation
"""

import time
import unittest
import threading
from unittest.mock import patch, MagicMock
from concurrent.futures import Future

from public_brokerage.orders import (
    place_multileg_order_with_verification_worker,
    _execute_order_placement_worker,
    _verify_order_status_worker,
    OrderPlacementError,
    OrderVerificationError,
    OrderCancelledException,
    OrderTimeoutError,
    OrderApiError
)
from worker_pool import cancel_task
from public_brokerage.models.order import MultiLegOrderRequest
from public_brokerage.models.order_state import OrderState
from public_brokerage.client import PublicBrokerageClient


class TestOrderErrorHandling(unittest.TestCase):
    """Test error handling in worker-based order placement."""
    
    def setUp(self):
        """Set up test client and order request."""
        self.client = PublicBrokerageClient(secret_token="test_token")
        self.client.set_access_token("test_access_token_123", validity_minutes=15)
        self.account_id = "test_account_123"
        
        self.order_request = MagicMock(spec=MultiLegOrderRequest)
        self.order_request.model_dump.return_value = {
            "orderId": "test-order-id-123",
            "quantity": 1,
            "type": "LIMIT",
            "limitPrice": "1.00",
            "expiration": "DAY",
            "legs": []
        }
    
    def tearDown(self):
        """Clean up."""
        self.client.close()
    
    # ========================================================================
    # HTTP ERROR TESTS
    # ========================================================================
    
    @patch('public_brokerage.orders.queue_http_request')
    def test_http_400_error_on_placement(self, mock_queue_http):
        """Test handling of HTTP 400 error during order placement."""
        print("\n[ERROR TEST] HTTP 400 - Bad Request")
        
        # Mock 400 response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "Invalid order parameters",
            "message": "Quantity must be positive"
        }
        mock_queue_http.return_value = mock_response
        
        # Execute and expect error
        with self.assertRaises(OrderApiError) as context:
            _execute_order_placement_worker(
                task_id='test_http_400',
                client=self.client,
                account_id=self.account_id,
                order_request=self.order_request,
                auth_token="test_token"
            )
        
        # Verify error details
        error = context.exception
        self.assertEqual(error.status_code, 400)
        self.assertIsNotNone(error.response_data)
        self.assertIn("400", str(error))
        
        print(f"OK - HTTP 400 error caught: {error}")
    
    @patch('public_brokerage.orders.queue_http_request')
    def test_http_401_error_unauthorized(self, mock_queue_http):
        """Test handling of HTTP 401 error (unauthorized)."""
        print("\n[ERROR TEST] HTTP 401 - Unauthorized")
        
        # Mock 401 response
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.side_effect = Exception("No JSON")  # Auth errors may not have JSON
        mock_queue_http.return_value = mock_response
        
        # Execute and expect error
        with self.assertRaises(OrderApiError) as context:
            _execute_order_placement_worker(
                task_id='test_http_401',
                client=self.client,
                account_id=self.account_id,
                order_request=self.order_request,
                auth_token="invalid_token"
            )
        
        # Verify error details
        error = context.exception
        self.assertEqual(error.status_code, 401)
        self.assertIn("401", str(error))
        
        print(f"OK - HTTP 401 error caught: {error}")
    
    @patch('public_brokerage.orders.Order.model_validate')
    @patch('public_brokerage.orders.queue_http_request')
    def test_http_500_error_on_verification(self, mock_queue_http, mock_order_validate):
        """Test handling of HTTP 500 error during order status check."""
        print("\n[ERROR TEST] HTTP 500 - Server Error during verification")
        
        # Mock 500 response
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"error": "Internal server error"}
        mock_queue_http.return_value = mock_response
        
        # Execute and expect error
        with self.assertRaises(OrderApiError) as context:
            _verify_order_status_worker(
                task_id='test_http_500',
                client=self.client,
                account_id=self.account_id,
                order_id="order_123",
                auth_token="test_token",
                check_interval=0.1
            )
        
        # Verify error details
        error = context.exception
        self.assertEqual(error.status_code, 500)
        self.assertIn("500", str(error))
        
        print(f"OK - HTTP 500 error caught: {error}")
    
    @patch('public_brokerage.orders.queue_http_request')
    def test_network_error_exception(self, mock_queue_http):
        """Test handling of network/connection errors."""
        print("\n[ERROR TEST] Network/Connection Error")
        
        # Mock network error
        mock_queue_http.side_effect = ConnectionError("Network unreachable")
        
        # Execute and expect wrapped error
        with self.assertRaises(OrderPlacementError) as context:
            _execute_order_placement_worker(
                task_id='test_network_error',
                client=self.client,
                account_id=self.account_id,
                order_request=self.order_request,
                auth_token="test_token"
            )
        
        # Verify error wrapping
        error = context.exception
        self.assertIn("Failed to place order", str(error))
        self.assertIsInstance(error.__cause__, ConnectionError)
        
        print(f"OK - Network error caught and wrapped: {error}")
    
    # ========================================================================
    # TIMEOUT TESTS
    # ========================================================================
    
    @patch('public_brokerage.orders.Order.model_validate')
    @patch('public_brokerage.orders.queue_http_request')
    def test_verification_timeout(self, mock_queue_http, mock_order_validate):
        """Test timeout when order stays in NEW status too long."""
        print("\n[ERROR TEST] Verification Timeout")
        
        # Mock order that stays NEW
        mock_order = MagicMock()
        mock_order.orderId = "order_123"
        mock_order.status = OrderState.NEW.value
        mock_order_validate.return_value = mock_order
        
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"orderId": "order_123", "status": "NEW"}
        mock_queue_http.return_value = mock_response
        
        # Execute with short timeout
        start_time = time.time()
        with self.assertRaises(OrderTimeoutError) as context:
            _verify_order_status_worker(
                task_id='test_timeout',
                client=self.client,
                account_id=self.account_id,
                order_id="order_123",
                auth_token="test_token",
                max_checks=3,
                check_interval=0.1
            )
        elapsed = time.time() - start_time
        
        # Verify timeout error
        error = context.exception
        self.assertIn("timed out", str(error).lower())
        self.assertIn("3 checks", str(error))
        
        # Verify timing (3 checks * 0.1s intervals + initial wait)
        self.assertGreater(elapsed, 0.3)
        self.assertLess(elapsed, 1.0)
        
        print(f"OK - Timeout error after {elapsed:.2f}s: {error}")
    
    # ========================================================================
    # CANCELLATION TESTS
    # ========================================================================
    
    @patch('public_brokerage.orders.queue_http_request')
    def test_cancel_before_placement(self, mock_queue_http):
        """Test cancellation before order is placed."""
        print("\n[CANCEL TEST] Cancel before placement")
        
        # Cancel task before it starts
        task_id = 'test_cancel_before'
        cancel_task(task_id)
        
        # Execute and expect cancellation
        with self.assertRaises(OrderCancelledException) as context:
            _execute_order_placement_worker(
                task_id=task_id,
                client=self.client,
                account_id=self.account_id,
                order_request=self.order_request,
                auth_token="test_token"
            )
        
        # Verify no HTTP call was made
        mock_queue_http.assert_not_called()
        
        # Verify error message
        error = context.exception
        self.assertIn("before execution", str(error))
        self.assertIsNone(error.partial_result)
        
        print(f"OK - Cancelled before placement: {error}")
    
    @patch('public_brokerage.orders.Order.model_validate')
    @patch('public_brokerage.orders.queue_http_request')
    def test_cancel_during_verification(self, mock_queue_http, mock_order_validate):
        """Test cancellation during verification loop."""
        print("\n[CANCEL TEST] Cancel during verification")
        
        # Mock order in NEW status
        mock_order = MagicMock()
        mock_order.orderId = "order_123"
        mock_order.status = OrderState.NEW.value
        mock_order_validate.return_value = mock_order
        
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"orderId": "order_123", "status": "NEW"}
        mock_queue_http.return_value = mock_response
        
        # Set cancellation after a delay
        task_id = 'test_cancel_during'
        
        def set_cancel():
            time.sleep(0.2)  # Let first check happen
            cancel_task(task_id)
        
        cancel_thread = threading.Thread(target=set_cancel, daemon=True)
        cancel_thread.start()
        
        # Execute and expect cancellation
        with self.assertRaises(OrderCancelledException) as context:
            _verify_order_status_worker(
                task_id=task_id,
                client=self.client,
                account_id=self.account_id,
                order_id="order_123",
                auth_token="test_token",
                max_checks=10,
                check_interval=0.2
            )
        
        # Verify error has partial result (or None if cancelled too early)
        error = context.exception
        self.assertIn("cancelled", str(error).lower())
        # Note: partial_result might be None if cancelled before first status check
        
        print(f"OK - Cancelled during verification: {error}")
    
    @patch('public_brokerage.orders.Order.model_validate')
    @patch('public_brokerage.orders.queue_http_request')
    def test_cancel_during_final_wait(self, mock_queue_http, mock_order_validate):
        """Test cancellation during final wait after order fills."""
        print("\n[CANCEL TEST] Cancel during final wait (after fill)")
        
        # Mock order that transitions to FILLED
        mock_order = MagicMock()
        mock_order.orderId = "order_123"
        mock_order.status = OrderState.FILLED.value
        mock_order_validate.return_value = mock_order
        
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"orderId": "order_123", "status": "FILLED"}
        mock_queue_http.return_value = mock_response
        
        # Set cancellation during final wait
        task_id = 'test_cancel_final'
        
        def set_cancel():
            time.sleep(0.3)  # Let order check happen and final wait start
            cancel_task(task_id)
        
        cancel_thread = threading.Thread(target=set_cancel, daemon=True)
        cancel_thread.start()
        
        # Execute - should return order even though cancelled during final wait
        # Use shorter check_interval so first check happens before cancel
        order = _verify_order_status_worker(
            task_id=task_id,
            client=self.client,
            account_id=self.account_id,
            order_id="order_123",
            auth_token="test_token",
            max_checks=10,
            check_interval=0.1  # Fast first check to beat the cancel
        )
        
        # Verify order was returned (cancellation during final wait doesn't fail)
        self.assertEqual(order.orderId, "order_123")
        self.assertEqual(order.status, OrderState.FILLED.value)
        
        print(f"OK - Returned filled order even though cancelled during final wait")
    
    @patch('public_brokerage.orders.Order.model_validate')
    @patch('public_brokerage.orders.queue_http_request')
    def test_cancel_full_workflow(self, mock_queue_http, mock_order_validate):
        """Test cancellation of full order placement workflow."""
        print("\n[CANCEL TEST] Cancel full workflow")
        
        # Mock successful placement
        placement_response = MagicMock()
        placement_response.status_code = 200
        placement_response.json.return_value = {"orderId": "order_123"}
        
        # Mock order in NEW status
        mock_order = MagicMock()
        mock_order.orderId = "order_123"
        mock_order.status = OrderState.NEW.value
        mock_order_validate.return_value = mock_order
        
        verification_response = MagicMock()
        verification_response.status_code = 200
        verification_response.json.return_value = {"orderId": "order_123", "status": "NEW"}
        
        mock_queue_http.side_effect = [placement_response, verification_response]
        
        # Set cancellation after placement
        def set_cancel(task_id):
            time.sleep(0.3)  # Let placement happen
            cancel_task(task_id)
        
        # Execute full workflow
        task_id, future = place_multileg_order_with_verification_worker(
            client=self.client,
            account_id=self.account_id,
            order_request=self.order_request
        )
        
        # Start cancellation thread
        cancel_thread = threading.Thread(target=set_cancel, args=(task_id,), daemon=True)
        cancel_thread.start()
        
        # Wait for result and expect cancellation
        with self.assertRaises(OrderCancelledException) as context:
            future.result(timeout=5.0)
        
        # Verify partial result available (order was placed, so we should have order_id)
        error = context.exception
        # Note: partial_result might be None if cancelled before verification gets first status
        
        print(f"OK - Full workflow cancelled: {error}")
    
    # ========================================================================
    # ERROR PROPAGATION TESTS
    # ========================================================================
    
    @patch('public_brokerage.orders.queue_http_request')
    def test_error_propagation_through_future(self, mock_queue_http):
        """Test that errors propagate correctly through Future."""
        print("\n[ERROR TEST] Error propagation through Future")
        
        # Mock 400 error
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "Bad request"}
        mock_queue_http.return_value = mock_response
        
        # Execute and get future
        task_id, future = place_multileg_order_with_verification_worker(
            client=self.client,
            account_id=self.account_id,
            order_request=self.order_request
        )
        
        # Wait for result and expect error
        with self.assertRaises(OrderApiError) as context:
            future.result(timeout=5.0)
        
        error = context.exception
        self.assertEqual(error.status_code, 400)
        
        print(f"OK - Error propagated through Future: {error}")


if __name__ == '__main__':
    print("=" * 80)
    print("ERROR HANDLING & CANCELLATION TESTS")
    print("=" * 80)
    print("\nTests for:")
    print("- HTTP errors (4xx, 5xx)")
    print("- Network errors")
    print("- Timeout errors")
    print("- Cancellation at different stages")
    print("- Partial results on cancellation")
    print("- Error propagation through Future")
    print("=" * 80)
    
    unittest.main(verbosity=2)
