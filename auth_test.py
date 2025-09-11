"""
Unit tests for authentication functions.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import os

from public_brokerage.auth import create_access_token, ensure_access_token
from public_brokerage.client import PublicBrokerageClient
from public_brokerage.models.auth import AccessTokenResponse


class TestAuth(unittest.TestCase):
    """Test cases for authentication functions."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = PublicBrokerageClient(secret_token="test_secret")
    
    def tearDown(self):
        """Clean up after tests."""
        self.client.close()
    
    @patch('public_brokerage.auth.os.getenv')
    def test_create_access_token_with_secret(self, mock_getenv):
        """Test creating access token with provided secret."""
        # Mock the API response
        mock_response = Mock()
        mock_response.json.return_value = {"accessToken": "test_token"}
        
        with patch.object(self.client, '_make_request', return_value=mock_response):
            with patch.object(self.client, '_handle_response') as mock_handle:
                mock_handle.return_value = AccessTokenResponse(accessToken="test_token")
                
                token = create_access_token(secret="test_secret", client=self.client)
                
                self.assertEqual(token, "test_token")
                # Should not call getenv since secret was provided
                mock_getenv.assert_not_called()
    
    @patch('public_brokerage.auth.os.getenv')
    def test_create_access_token_from_env(self, mock_getenv):
        """Test creating access token from environment variable."""
        mock_getenv.return_value = "env_secret"
        
        mock_response = Mock()
        with patch.object(self.client, '_make_request', return_value=mock_response):
            with patch.object(self.client, '_handle_response') as mock_handle:
                mock_handle.return_value = AccessTokenResponse(accessToken="env_token")
                
                token = create_access_token(client=self.client)
                
                self.assertEqual(token, "env_token")
                mock_getenv.assert_called_with("PUBLIC_SECRET_TOKEN")
    
    @patch('public_brokerage.auth.os.getenv')
    def test_create_access_token_no_secret(self, mock_getenv):
        """Test creating access token with no secret available."""
        mock_getenv.return_value = None
        
        with self.assertRaises(ValueError) as context:
            create_access_token(client=self.client)
        
        self.assertIn("Secret token is required", str(context.exception))
    
    def test_create_access_token_custom_validity(self):
        """Test creating access token with custom validity."""
        mock_response = Mock()
        
        with patch.object(self.client, '_make_request', return_value=mock_response) as mock_request:
            with patch.object(self.client, '_handle_response') as mock_handle:
                mock_handle.return_value = AccessTokenResponse(accessToken="test_token")
                
                token = create_access_token(
                    secret="test_secret", 
                    validity_minutes=30, 
                    client=self.client
                )
                
                # Check that the request was made with correct validity
                call_args = mock_request.call_args
                request_data = call_args[1]['data']
                self.assertEqual(request_data['validityInMinutes'], 30)
    
    def test_create_access_token_sets_client_token(self):
        """Test that create_access_token sets the token on the client."""
        mock_response = Mock()
        
        with patch.object(self.client, '_make_request', return_value=mock_response):
            with patch.object(self.client, '_handle_response') as mock_handle:
                with patch.object(self.client, 'set_access_token') as mock_set_token:
                    mock_handle.return_value = AccessTokenResponse(accessToken="test_token")
                    
                    create_access_token(secret="test_secret", client=self.client)
                    
                    mock_set_token.assert_called_once_with("test_token", 15)
    
    def test_create_access_token_creates_client(self):
        """Test that create_access_token creates client if none provided."""
        with patch('public_brokerage.auth.PublicBrokerageClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            
            mock_response = Mock()
            mock_client._make_request.return_value = mock_response
            mock_client._handle_response.return_value = AccessTokenResponse(accessToken="test_token")
            mock_client.set_access_token.return_value = None
            
            token = create_access_token(secret="test_secret")
            
            self.assertEqual(token, "test_token")
            mock_client_class.assert_called_once()
    
    def test_ensure_access_token_valid_token(self):
        """Test ensure_access_token with valid existing token."""
        # Mock valid token
        with patch.object(self.client, 'is_access_token_valid', return_value=True):
            with patch.object(self.client, 'get_access_token', return_value="valid_token"):
                
                token = ensure_access_token(self.client)
                
                self.assertEqual(token, "valid_token")
    
    def test_ensure_access_token_creates_new(self):
        """Test ensure_access_token creates new token when needed."""
        # Mock invalid token initially
        with patch.object(self.client, 'is_access_token_valid', return_value=False):
            with patch('public_brokerage.auth.create_access_token') as mock_create:
                mock_create.return_value = "new_token"
                
                token = ensure_access_token(self.client)
                
                self.assertEqual(token, "new_token")
                mock_create.assert_called_once_with(
                    secret=self.client.secret_token,
                    client=self.client
                )
    
    def test_ensure_access_token_no_secret(self):
        """Test ensure_access_token with no secret token."""
        client_no_secret = PublicBrokerageClient()
        
        with patch.object(client_no_secret, 'is_access_token_valid', return_value=False):
            with self.assertRaises(ValueError) as context:
                ensure_access_token(client_no_secret)
            
            self.assertIn("Secret token is required", str(context.exception))
        
        client_no_secret.close()


if __name__ == '__main__':
    unittest.main()
