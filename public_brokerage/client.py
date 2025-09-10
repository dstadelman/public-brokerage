"""
Base client for the Public Brokerage API.
"""

import json
import logging
import time
from typing import Any, Dict, Optional, Union
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models.auth import AccessTokenResponse


class PublicBrokerageClient:
    """Base client for Public Brokerage API interactions."""
    
    def __init__(
        self,
        secret_token: Optional[str] = None,
        base_url: str = "https://public.com",
        timeout: int = 30,
        max_retries: int = 3,
        debug: bool = False
    ):
        """
        Initialize the Public Brokerage API client.
        
        Args:
            secret_token: Personal secret token from Public account settings
            base_url: Base URL for the API
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            debug: Enable debug logging
        """
        self.secret_token = secret_token
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.debug = debug
        
        # Initialize access token storage
        self._access_token: Optional[str] = None
        self._access_token_expires_at: Optional[float] = None
        
        # Set up logging
        self.logger = logging.getLogger(__name__)
        if debug:
            logging.basicConfig(level=logging.DEBUG)
        
        # Set up session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PUT", "DELETE"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
    def set_access_token(self, access_token: str, validity_minutes: int = 15) -> None:
        """
        Set the access token and its expiration time.
        
        Args:
            access_token: The access token
            validity_minutes: Token validity in minutes
        """
        self._access_token = access_token
        self._access_token_expires_at = time.time() + (validity_minutes * 60)
        self.logger.debug("Access token set with %d minutes validity", validity_minutes)
    
    def is_access_token_valid(self) -> bool:
        """
        Check if the current access token is valid.
        
        Returns:
            True if token is valid, False otherwise
        """
        if not self._access_token or not self._access_token_expires_at:
            return False
        
        # Add 30 second buffer before expiration
        return time.time() < (self._access_token_expires_at - 30)
    
    def get_access_token(self) -> Optional[str]:
        """
        Get the current access token if valid.
        
        Returns:
            Access token if valid, None otherwise
        """
        if self.is_access_token_valid():
            return self._access_token
        return None
    
    def _get_headers(self, include_auth: bool = True) -> Dict[str, str]:
        """
        Get request headers.
        
        Args:
            include_auth: Whether to include authorization header
            
        Returns:
            Headers dictionary
        """
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "public-brokerage-python/0.1.0"
        }
        
        if include_auth:
            access_token = self.get_access_token()
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
        
        return headers
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        include_auth: bool = True,
        base_url_override: Optional[str] = None
    ) -> requests.Response:
        """
        Make an HTTP request to the API.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            data: Request body data
            params: Query parameters
            include_auth: Whether to include authorization
            base_url_override: Override base URL for specific endpoints
            
        Returns:
            Response object
            
        Raises:
            requests.exceptions.RequestException: For HTTP errors
        """
        base_url = base_url_override or self.base_url
        url = urljoin(base_url + "/", endpoint.lstrip("/"))
        headers = self._get_headers(include_auth=include_auth)
        
        request_data = {
            "method": method,
            "url": url,
            "headers": headers,
            "timeout": self.timeout
        }
        
        if data is not None:
            request_data["json"] = data
        
        if params is not None:
            request_data["params"] = params
        
        self.logger.debug("Making %s request to %s", method, url)
        if self.debug and data:
            self.logger.debug("Request data: %s", json.dumps(data, indent=2))
        
        try:
            response = self.session.request(**request_data)
            
            self.logger.debug("Response status: %d", response.status_code)
            if self.debug and response.text:
                self.logger.debug("Response body: %s", response.text)
            
            # Raise for HTTP errors
            response.raise_for_status()
            
            return response
            
        except requests.exceptions.RequestException as e:
            self.logger.error("Request failed: %s", str(e))
            if hasattr(e, 'response') and e.response is not None:
                self.logger.error("Response status: %d", e.response.status_code)
                self.logger.error("Response body: %s", e.response.text)
            raise
    
    def _handle_response(
        self,
        response: requests.Response,
        expected_model: Optional[type] = None
    ) -> Union[Dict[str, Any], Any]:
        """
        Handle API response and parse JSON.
        
        Args:
            response: HTTP response
            expected_model: Expected Pydantic model class
            
        Returns:
            Parsed response data or model instance
        """
        if response.status_code == 204:
            # No content response
            return None
        
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            self.logger.error("Failed to parse JSON response: %s", str(e))
            raise ValueError(f"Invalid JSON response: {str(e)}")
        
        if expected_model:
            try:
                return expected_model(**data)
            except Exception as e:
                self.logger.error("Failed to parse response into %s: %s", 
                                expected_model.__name__, str(e))
                self.logger.error("Response data: %s", json.dumps(data, indent=2))
                raise ValueError(f"Failed to parse response: {str(e)}")
        
        return data
    
    def close(self) -> None:
        """Close the HTTP session."""
        self.session.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
