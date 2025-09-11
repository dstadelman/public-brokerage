"""
Unit tests for the PublicBrokerageClient base class.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import time
from requests.exceptions import HTTPError, RequestException

from public_brokerage.client import PublicBrokerageClient


class TestPublicBrokerageClient(unittest.TestCase):
    """Test cases for PublicBrokerageClient."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = PublicBrokerageClient(
            secret_token="test_secret",
            base_url="https://test.com",
            timeout=10,
            max_retries=1,
            debug=False
        )
    
    def tearDown(self):
        """Clean up after tests."""
        self.client.close()
    
    def test_init(self):
        """Test client initialization."""
        self.assertEqual(self.client.secret_token, "test_secret")
        self.assertEqual(self.client.base_url, "https://test.com")
        self.assertEqual(self.client.timeout, 10)
        self.assertEqual(self.client.max_retries, 1)
        self.assertFalse(self.client.debug)
        self.assertIsNone(self.client._access_token)
        self.assertIsNone(self.client._access_token_expires_at)
    
    def test_set_access_token(self):
        """Test setting access token."""
        token = "test_token"
        validity = 15
        
        # Mock time.time()
        with patch('time.time', return_value=1000.0):
            self.client.set_access_token(token, validity)
        
        self.assertEqual(self.client._access_token, token)
        self.assertEqual(self.client._access_token_expires_at, 1000.0 + (15 * 60))
    
    def test_is_access_token_valid(self):
        """Test access token validation."""
        # No token set
        self.assertFalse(self.client.is_access_token_valid())
        
        # Set token with future expiration
        with patch('time.time', return_value=1000.0):
            self.client.set_access_token("token", 15)
        
        # Check valid token
        with patch('time.time', return_value=1000.0):
            self.assertTrue(self.client.is_access_token_valid())
        
        # Check expired token
        with patch('time.time', return_value=2000.0):
            self.assertFalse(self.client.is_access_token_valid())
    
    def test_get_access_token(self):
        """Test getting access token."""
        # No token set
        self.assertIsNone(self.client.get_access_token())
        
        # Set valid token
        with patch('time.time', return_value=1000.0):
            self.client.set_access_token("token", 15)
            self.assertEqual(self.client.get_access_token(), "token")
        
        # Expired token
        with patch('time.time', return_value=2000.0):
            self.assertIsNone(self.client.get_access_token())
    
    def test_get_headers_without_auth(self):
        """Test getting headers without authentication."""
        headers = self.client._get_headers(include_auth=False)
        
        expected = {
            "Content-Type": "application/json",
            "User-Agent": "public-brokerage-python/0.1.0"
        }
        
        self.assertEqual(headers, expected)
    
    def test_get_headers_with_auth(self):
        """Test getting headers with authentication."""
        # Set valid token and ensure it stays valid during header generation
        with patch('time.time', return_value=1000.0):
            self.client.set_access_token("test_token", 15)
            headers = self.client._get_headers(include_auth=True)
        
        expected = {
            "Content-Type": "application/json",
            "User-Agent": "public-brokerage-python/0.1.0",
            "Authorization": "Bearer test_token"
        }
        
        self.assertEqual(headers, expected)
    
    @patch('public_brokerage.client.requests.Session.request')
    def test_make_request_success(self, mock_request):
        """Test successful API request."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"success": true}'
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response
        
        response = self.client._make_request("GET", "/test")
        
        self.assertEqual(response, mock_response)
        mock_request.assert_called_once()
    
    @patch('public_brokerage.client.requests.Session.request')
    def test_make_request_with_data(self, mock_request):
        """Test API request with JSON data."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response
        
        test_data = {"key": "value"}
        self.client._make_request("POST", "/test", data=test_data)
        
        # Verify request was made with JSON data
        call_args = mock_request.call_args
        self.assertEqual(call_args[1]["json"], test_data)
    
    @patch('public_brokerage.client.requests.Session.request')
    def test_make_request_with_params(self, mock_request):
        """Test API request with query parameters."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response
        
        test_params = {"param1": "value1"}
        self.client._make_request("GET", "/test", params=test_params)
        
        # Verify request was made with params
        call_args = mock_request.call_args
        self.assertEqual(call_args[1]["params"], test_params)
    
    @patch('public_brokerage.client.requests.Session.request')
    def test_make_request_http_error(self, mock_request):
        """Test API request with HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_response.raise_for_status.side_effect = HTTPError("400 Client Error")
        mock_request.return_value = mock_response
        
        with self.assertRaises(HTTPError):
            self.client._make_request("GET", "/test")
    
    def test_handle_response_no_content(self):
        """Test handling response with no content."""
        mock_response = Mock()
        mock_response.status_code = 204
        
        result = self.client._handle_response(mock_response)
        self.assertIsNone(result)
    
    def test_handle_response_json(self):
        """Test handling JSON response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"key": "value"}
        
        result = self.client._handle_response(mock_response)
        self.assertEqual(result, {"key": "value"})
    
    def test_handle_response_with_model(self):
        """Test handling response with Pydantic model."""
        from pydantic import BaseModel
        
        class TestModel(BaseModel):
            key: str
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"key": "value"}
        
        result = self.client._handle_response(mock_response, TestModel)
        self.assertIsInstance(result, TestModel)
        self.assertEqual(result.key, "value")
    
    def test_handle_response_invalid_json(self):
        """Test handling response with invalid JSON."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        
        with self.assertRaises(ValueError):
            self.client._handle_response(mock_response)
    
    def test_context_manager(self):
        """Test client as context manager."""
        with patch.object(self.client, 'close') as mock_close:
            with self.client as client:
                self.assertEqual(client, self.client)
            mock_close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
