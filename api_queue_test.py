"""
Test HTTP request queuing in API queue (Phase 2 verification).
"""

import time
import unittest
from unittest.mock import patch, MagicMock
from api_queue import ApiRequestQueue, HttpApiRequest, queue_http_request


class TestHttpRequestQueue(unittest.TestCase):
    """Test HTTP request queuing functionality."""
    
    def setUp(self):
        """Create a fresh API queue for each test."""
        self.api_queue = ApiRequestQueue()  # NO DELAYS
        self.api_queue.start()
    
    def tearDown(self):
        """Stop the API queue after each test."""
        self.api_queue.stop()
    
    @patch('api_queue.requests.request')
    def test_http_get_request(self, mock_request):
        """Test that HTTP GET requests are queued and executed correctly."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success"}
        mock_request.return_value = mock_response
        
        # Queue HTTP request
        start_time = time.time()
        response = self.api_queue.queue_http_request(
            method="GET",
            endpoint="/test",
            auth_token="test_token_123"
        )
        elapsed = time.time() - start_time
        
        # Verify
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "success"})
        
        # Verify the actual HTTP call was made correctly
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        self.assertEqual(call_args[1]['method'], 'GET')
        self.assertEqual(call_args[1]['url'], 'https://api.public.com/test')
        self.assertEqual(call_args[1]['headers']['Authorization'], 'Bearer test_token_123')
        
        print(f"✅ Test 1: HTTP GET request queued and executed in {elapsed:.2f}s")
    
    @patch('api_queue.requests.request')
    def test_http_post_request(self, mock_request):
        """Test that HTTP POST requests are queued and executed correctly."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"order_id": "12345"}
        mock_request.return_value = mock_response
        
        # Queue HTTP request with data
        order_data = {
            "symbol": "SPY",
            "quantity": 100,
            "side": "buy"
        }
        
        response = self.api_queue.queue_http_request(
            method="POST",
            endpoint="/orders",
            data=order_data,
            auth_token="test_token_123"
        )
        
        # Verify
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["order_id"], "12345")
        
        # Verify the actual HTTP call
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        self.assertEqual(call_args[1]['method'], 'POST')
        self.assertEqual(call_args[1]['url'], 'https://api.public.com/orders')
        self.assertEqual(call_args[1]['json'], order_data)
        
        print(f"✅ Test 2: HTTP POST request with data queued and executed")
    
    @patch('api_queue.requests.request')
    def test_no_throttling_fast_execution(self, mock_request):
        """Test that multiple requests execute immediately with NO delays."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response
        
        # Queue 5 requests (mix of GET and POST)
        start_time = time.time()
        for i in range(5):
            method = "POST" if i % 2 == 0 else "GET"
            self.api_queue.queue_http_request(
                method=method,
                endpoint=f"/test/{i}",
                data={"test": i} if method == "POST" else None,
                auth_token="test_token_123"
            )
        elapsed = time.time() - start_time
        
        # Should be FAST - no artificial delays
        # Allow up to 0.5s for actual execution overhead
        self.assertLess(elapsed, 0.5, f"Requests took {elapsed:.2f}s - should be < 0.5s with NO delays")
        self.assertEqual(mock_request.call_count, 5)
        
        print(f"✅ Test 3: 5 requests (GET/POST) executed immediately in {elapsed:.2f}s (NO DELAYS)")
    
    @patch('api_queue.requests.request')
    def test_post_requests_no_delay(self, mock_request):
        """Test that POST requests have NO artificial delay."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_request.return_value = mock_response
        
        # Queue 3 POST requests
        start_time = time.time()
        for i in range(3):
            self.api_queue.queue_http_request(
                method="POST",
                endpoint=f"/orders/{i}",
                data={"test": i},
                auth_token="test_token_123"
            )
        elapsed = time.time() - start_time
        
        # Should be FAST - no 5-second delays!
        self.assertLess(elapsed, 0.5, f"POST requests took {elapsed:.2f}s - should be < 0.5s")
        self.assertEqual(mock_request.call_count, 3)
        
        print(f"✅ Test 4: 3 POST requests executed immediately in {elapsed:.2f}s (NO DELAYS)")
    
    @patch('api_queue.requests.request')
    def test_convenience_function(self, mock_request):
        """Test the convenience function queue_http_request()."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response
        
        # Use convenience function
        response = queue_http_request(
            method="GET",
            endpoint="/test",
            auth_token="test_token_123"
        )
        
        self.assertEqual(response.status_code, 200)
        mock_request.assert_called_once()
        
        print(f"✅ Test 5: Convenience function queue_http_request() works")
    
    def test_http_request_dataclass(self):
        """Test HttpApiRequest dataclass creation."""
        http_req = HttpApiRequest(
            request_id="test123",
            method="POST",
            endpoint="/orders",
            data={"symbol": "SPY"},
            auth_token="token123"
        )
        
        self.assertEqual(http_req.method, "POST")
        self.assertEqual(http_req.endpoint, "/orders")
        self.assertIsNotNone(http_req.result_event)
        self.assertIsNotNone(http_req.created_at)
        
        print(f"✅ Test 6: HttpApiRequest dataclass works correctly")


if __name__ == '__main__':
    print("Testing Phase 2: HTTP Request Queuing (NO DELAYS)")
    print("=" * 60)
    
    unittest.main(verbosity=2)
