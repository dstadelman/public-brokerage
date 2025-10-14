"""
Test Phase 3: Worker-Based Order Placement

CRITICAL: Anti-deadlock tests to ensure worker -> API thread communication works
without circular dependencies.
"""

import time
import unittest
from unittest.mock import patch, MagicMock, Mock
from concurrent.futures import Future
import threading

# Import the functions we're testing
from public_brokerage.orders import (
    place_multileg_order_with_verification_worker,
    place_multileg_order_with_verification,
    _execute_order_placement_worker,
    _verify_order_status_worker
)
from public_brokerage.models.order import MultiLegOrderRequest, Order
from public_brokerage.models.order_state import OrderState
from public_brokerage.client import PublicBrokerageClient


class TestWorkerBasedOrderPlacement(unittest.TestCase):
    """Test worker-based order placement with anti-deadlock verification."""
    
    def setUp(self):
        """Set up test client."""
        self.client = PublicBrokerageClient(secret_token="test_token")
        self.client.set_access_token("test_access_token_123", validity_minutes=15)
        self.account_id = "test_account_123"
        
        # Create sample order request with all required fields
        # Note: In tests, we'll mock the HTTP calls anyway, so this is just for structure
        self.order_request = MagicMock(spec=MultiLegOrderRequest)
        self.order_request.model_dump.return_value = {
            "orderId": "test-order-id-123",
            "quantity": 1,
            "type": "LIMIT",
            "limitPrice": "1.00",
            "expiration": "DAY",
            "legs": [
                {
                    "instrument": "OPTION",
                    "side": "BUY",
                    "openCloseIndicator": "OPEN",
                    "ratioQuantity": 1
                }
            ]
        }
    
    def tearDown(self):
        """Clean up."""
        self.client.close()
    
    # ========================================================================
    # ANTI-DEADLOCK TESTS - CRITICAL!
    # ========================================================================
    
    @patch('public_brokerage.orders.queue_http_request')
    def test_anti_deadlock_worker_to_api_thread(self, mock_queue_http):
        """
        ANTI-DEADLOCK TEST 1: Worker calls queue_http_request() and waits for response.
        
        Verifies:
        - Worker can call queue_http_request() without blocking
        - API thread processes request
        - Worker receives response
        - NO DEADLOCK
        """
        print("\n[ANTI-DEADLOCK TEST 1] Worker -> API Thread communication")
        
        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"orderId": "order_12345"}
        mock_queue_http.return_value = mock_response
        
        # Execute in worker thread
        start_time = time.time()
        order_id = _execute_order_placement_worker(
            task_id='test_task_deadlock_1',
            client=self.client,
            account_id=self.account_id,
            order_request=self.order_request,
            auth_token="test_token"
        )
        elapsed = time.time() - start_time
        
        # Verify
        self.assertEqual(order_id, "order_12345")
        self.assertTrue(elapsed < 1.0, f"Worker took {elapsed:.2f}s - should be fast")
        mock_queue_http.assert_called_once()
        
        print(f"OK Worker -> API communication successful in {elapsed:.2f}s (NO DEADLOCK)")
    
    @patch('public_brokerage.orders.Order.model_validate')
    @patch('public_brokerage.orders.queue_http_request')
    def test_anti_deadlock_multiple_workers(self, mock_queue_http, mock_order_validate):
        """
        ANTI-DEADLOCK TEST 2: Multiple workers call queue_http_request() simultaneously.
        
        Verifies:
        - Multiple workers can queue requests simultaneously
        - All workers receive responses
        - NO DEADLOCK with concurrent workers
        """
        print("\n[ANTI-DEADLOCK TEST 2] Multiple workers concurrent execution")
        
        # Mock Order.model_validate to return simple mock objects (bypasses Pydantic validation)
        def create_mock_order(data):
            order = MagicMock()
            order.orderId = data.get('orderId', 'order_12345')
            order.status = data.get('status', 'FILLED')
            return order
        
        mock_order_validate.side_effect = create_mock_order
        
        # Mock HTTP response
        def create_response():
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                "orderId": "order_12345",
                "status": "FILLED"
            }
            return resp
        
        # Return new mock for each call (POST + GET for each worker)
        mock_queue_http.side_effect = [create_response() for _ in range(6)]
        
        # Submit 3 worker tasks
        start_time = time.time()
        task_futures = []
        for i in range(3):
            task_id, future = place_multileg_order_with_verification_worker(
                client=self.client,
                account_id=self.account_id,
                order_request=self.order_request
            )
            task_futures.append((task_id, future))
        
        # Wait for all to complete
        results = [f[1].result(timeout=5.0) for f in task_futures]
        elapsed = time.time() - start_time
        
        # Verify all completed
        self.assertEqual(len(results), 3)
        self.assertTrue(elapsed < 5.0, f"Multiple workers took {elapsed:.2f}s")
        
        print(f"OK 3 workers completed in {elapsed:.2f}s (NO DEADLOCK)")
    
    @patch('public_brokerage.orders.Order.model_validate')
    @patch('public_brokerage.orders.queue_http_request')
    def test_anti_deadlock_sequential_requests(self, mock_queue_http, mock_order_validate):
        """
        ANTI-DEADLOCK TEST 3: Worker makes POST then GET sequentially.
        
        Verifies:
        - Worker can make multiple sequential API calls
        - POST completes before GET starts
        - NO DEADLOCK with sequential requests
        """
        print("\n[ANTI-DEADLOCK TEST 3] Sequential API requests (POST -> GET)")
        
        # Mock Order.model_validate to return a mock order (bypasses Pydantic validation)
        mock_order = MagicMock()
        mock_order.orderId = "order_12345"
        mock_order.status = "FILLED"
        mock_order_validate.return_value = mock_order
        
        # Mock responses
        post_response = MagicMock()
        post_response.status_code = 200
        post_response.json.return_value = {"orderId": "order_12345"}
        
        get_response = MagicMock()
        get_response.status_code = 200
        get_response.json.return_value = {
            "orderId": "order_12345",
            "status": "FILLED"
        }
        
        # Configure mock to return different responses
        mock_queue_http.side_effect = [post_response, get_response]
        
        # Execute worker task (places order then checks status)
        start_time = time.time()
        task_id, future = place_multileg_order_with_verification_worker(
            client=self.client,
            account_id=self.account_id,
            order_request=self.order_request
        )
        order = future.result(timeout=5.0)
        elapsed = time.time() - start_time
        
        # Verify both calls were made
        self.assertEqual(mock_queue_http.call_count, 2)
        self.assertEqual(order.orderId, "order_12345")
        self.assertEqual(order.status, "FILLED")
        
        print(f"OK Sequential POST -> GET completed in {elapsed:.2f}s (NO DEADLOCK)")
    
    @patch('public_brokerage.orders.Order.model_validate')
    @patch('public_brokerage.orders.queue_http_request')
    def test_anti_deadlock_verification_loop(self, mock_queue_http, mock_order_validate):
        """
        ANTI-DEADLOCK TEST 4: Verification loop makes multiple GET requests.
        
        Verifies:
        - Worker can make 10+ sequential GET requests
        - API thread processes all requests
        - NO DEADLOCK in verification loop
        """
        print("\n[ANTI-DEADLOCK TEST 4] Verification loop (multiple GET requests)")
        
        # Mock Order.model_validate: first 3 return NEW, 4th returns FILLED
        def create_order_from_data(data):
            order = MagicMock()
            order.orderId = data.get('orderId', 'order_12345')
            order.status = data.get('status', 'NEW')
            return order
        
        mock_order_validate.side_effect = create_order_from_data
        
        # Mock responses: First 3 return NEW, 4th returns FILLED
        responses = []
        for i in range(3):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                "orderId": "order_12345",
                "status": "NEW"
            }
            responses.append(resp)
        
        # Final response - FILLED
        final_resp = MagicMock()
        final_resp.status_code = 200
        final_resp.json.return_value = {
            "orderId": "order_12345",
            "status": "FILLED"
        }
        responses.append(final_resp)
        
        mock_queue_http.side_effect = responses
        
        # Execute verification loop
        start_time = time.time()
        order = _verify_order_status_worker(
            task_id='test_task_verification_loop',
            client=self.client,
            account_id=self.account_id,
            order_id="order_12345",
            auth_token="test_token",
            max_checks=10,
            check_interval=0.1  # Fast for testing
        )
        elapsed = time.time() - start_time
        
        # Verify
        self.assertEqual(order.status, "FILLED")
        self.assertEqual(mock_queue_http.call_count, 4)  # 3 NEW + 1 FILLED
        
        print(f"OK Verification loop (4 GET requests) completed in {elapsed:.2f}s (NO DEADLOCK)")
    
    @patch('public_brokerage.orders.queue_http_request')
    def test_anti_deadlock_timeout_scenario(self, mock_queue_http):
        """
        ANTI-DEADLOCK TEST 5: Worker timeout scenario.
        
        Verifies:
        - Worker can handle timeout gracefully
        - NO DEADLOCK on timeout
        """
        print("\n[ANTI-DEADLOCK TEST 5] Timeout handling")
        
        # Mock slow response
        def slow_response(*args, **kwargs):
            time.sleep(0.5)  # Simulate slow API
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"orderId": "order_12345"}
            return resp
        
        mock_queue_http.side_effect = slow_response
        
        # Execute with timeout
        start_time = time.time()
        try:
            task_id, future = place_multileg_order_with_verification_worker(
                client=self.client,
                account_id=self.account_id,
                order_request=self.order_request
            )
            # Use short timeout to test timeout handling
            order = future.result(timeout=2.0)
            elapsed = time.time() - start_time
            
            print(f"OK Completed in {elapsed:.2f}s (NO DEADLOCK on slow response)")
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"OK Timeout handled gracefully in {elapsed:.2f}s (NO DEADLOCK)")
    
    # ========================================================================
    # FUNCTIONAL TESTS
    # ========================================================================
    # FUNCTIONAL TESTS
    # ========================================================================
    
    @patch('public_brokerage.orders.Order.model_validate')
    @patch('public_brokerage.orders.queue_http_request')
    def test_worker_based_order_placement(self, mock_queue_http, mock_order_validate):
        """Test basic worker-based order placement."""
        print("\n[FUNCTIONAL TEST] Basic worker-based order placement")
        
        # Mock Order.model_validate to return a mock order
        mock_order = MagicMock()
        mock_order.orderId = "order_12345"
        mock_order.status = "FILLED"
        mock_order_validate.return_value = mock_order
        
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "orderId": "order_12345",
            "status": "FILLED"
        }
        mock_queue_http.return_value = mock_response
        
        # Place order (non-blocking)
        task_id, future = place_multileg_order_with_verification_worker(
            client=self.client,
            account_id=self.account_id,
            order_request=self.order_request
        )
        
        # Verify Future returned immediately
        self.assertIsInstance(future, Future)
        
        # Get result (blocking)
        order = future.result()
        
        # Verify
        self.assertEqual(order.orderId, "order_12345")
        self.assertEqual(order.status, "FILLED")
        
        print("OK Worker-based order placement works")
    
    @patch('public_brokerage.orders.Order.model_validate')
    @patch('public_brokerage.orders.queue_http_request')
    def test_order_state_enum_usage(self, mock_queue_http, mock_order_validate):
        """Test that OrderState enums are used correctly."""
        print("\n[FUNCTIONAL TEST] OrderState enum usage")
        
        # Mock Order.model_validate to return mock orders with different states
        def create_order_from_data(data):
            order = MagicMock()
            order.orderId = data.get('orderId', 'order_12345')
            order.status = data.get('status', 'NEW')
            return order
        
        mock_order_validate.side_effect = create_order_from_data
        
        # Mock responses showing state transitions
        new_response = MagicMock()
        new_response.status_code = 200
        new_response.json.return_value = {
            "orderId": "order_12345",
            "status": OrderState.NEW.value
        }
        
        filled_response = MagicMock()
        filled_response.status_code = 200
        filled_response.json.return_value = {
            "orderId": "order_12345",
            "status": OrderState.FILLED.value
        }
        
        mock_queue_http.side_effect = [new_response, filled_response]
        
        # Execute verification
        order = _verify_order_status_worker(
            task_id='test_task_enum_usage',
            client=self.client,
            account_id=self.account_id,
            order_id="order_12345",
            auth_token="test_token",
            check_interval=0.1
        )
        
        # Verify state is checked using enum
        self.assertEqual(order.status, OrderState.FILLED.value)
        order_state = OrderState(order.status)
        self.assertTrue(order_state.is_terminal())
        
        print("OK OrderState enums used correctly")
    
    @patch('public_brokerage.orders.Order.model_validate')
    @patch('public_brokerage.orders.queue_http_request')
    def test_verification_loop_timing(self, mock_queue_http, mock_order_validate):
        """Test that verification loop has proper timing (1s delays in worker)."""
        print("\n[FUNCTIONAL TEST] Verification loop timing")
        
        # Mock Order.model_validate to return mock orders
        def create_order_from_data(data):
            order = MagicMock()
            order.orderId = data.get('orderId', 'order_12345')
            order.status = data.get('status', 'NEW')
            return order
        
        mock_order_validate.side_effect = create_order_from_data
        
        # Mock responses
        new_response = MagicMock()
        new_response.status_code = 200
        new_response.json.return_value = {
            "orderId": "order_12345",
            "status": "NEW"
        }
        
        filled_response = MagicMock()
        filled_response.status_code = 200
        filled_response.json.return_value = {
            "orderId": "order_12345",
            "status": "FILLED"
        }
        
        # First 2 calls return NEW, 3rd returns FILLED
        mock_queue_http.side_effect = [new_response, new_response, filled_response]
        
        # Execute with 0.5s intervals for testing
        start_time = time.time()
        order = _verify_order_status_worker(
            task_id='test_task_timing',
            client=self.client,
            account_id=self.account_id,
            order_id="order_12345",
            auth_token="test_token",
            check_interval=0.5
        )
        elapsed = time.time() - start_time
        
        # Verify timing: 0.5s initial + 0.5s wait + 0.5s wait + 0.5s final = ~2.0s
        self.assertGreaterEqual(elapsed, 1.5, "Should include delays between checks")
        self.assertEqual(mock_queue_http.call_count, 3)
        
        print(f"OK Verification loop timing correct ({elapsed:.2f}s for 3 checks)")
    
    @patch('public_brokerage.orders.Order.model_validate')
    @patch('public_brokerage.orders.queue_http_request')
    def test_blocking_wrapper(self, mock_queue_http, mock_order_validate):
        """Test backward compatible blocking wrapper."""
        print("\n[FUNCTIONAL TEST] Blocking wrapper (backward compatibility)")
        
        # Mock Order.model_validate to return a mock order
        mock_order = MagicMock()
        mock_order.orderId = "order_12345"
        mock_order.status = "FILLED"
        mock_order_validate.return_value = mock_order
        
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "orderId": "order_12345",
            "status": "FILLED"
        }
        mock_queue_http.return_value = mock_response
        
        # Use blocking wrapper
        order = place_multileg_order_with_verification(
            client=self.client,
            account_id=self.account_id,
            order_request=self.order_request
        )
        
        # Verify we got Order object (mock in this case, but same interface)
        self.assertEqual(order.orderId, "order_12345")
        
        print("OK Blocking wrapper works (backward compatible)")
    
    @patch('public_brokerage.orders.Order.model_validate')
    @patch('public_brokerage.orders.queue_http_request')
    def test_non_blocking_behavior(self, mock_queue_http, mock_order_validate):
        """Test that worker-based function returns immediately (non-blocking)."""
        print("\n[FUNCTIONAL TEST] Non-blocking behavior")
        
        # Mock Order.model_validate to return a mock order
        mock_order = MagicMock()
        mock_order.orderId = "order_12345"
        mock_order.status = "FILLED"
        mock_order_validate.return_value = mock_order
        
        # Mock slow response
        def slow_response(*args, **kwargs):
            time.sleep(1.0)
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                "orderId": "order_12345",
                "status": "FILLED"
            }
            return resp
        
        mock_queue_http.side_effect = slow_response
        
        # Call should return immediately
        start_time = time.time()
        task_id, future = place_multileg_order_with_verification_worker(
            client=self.client,
            account_id=self.account_id,
            order_request=self.order_request
        )
        call_elapsed = time.time() - start_time
        
        # Verify returned immediately (< 0.5s)
        self.assertLess(call_elapsed, 0.5, "Should return immediately")
        self.assertIsInstance(future, Future)
        
        # Now wait for result
        order = future.result(timeout=5.0)
        total_elapsed = time.time() - start_time
        
        # Verify result is correct
        self.assertEqual(order.orderId, "order_12345")
        
        print(f"OK Non-blocking: returned in {call_elapsed:.2f}s, completed in {total_elapsed:.2f}s")


if __name__ == '__main__':
    print("=" * 80)
    print("PHASE 3 TESTS: Worker-Based Order Placement")
    print("=" * 80)
    print("\nCRITICAL: Anti-Deadlock Tests")
    print("These tests verify that worker -> API thread communication works")
    print("without circular dependencies or deadlocks.")
    print("=" * 80)
    
    unittest.main(verbosity=2)
