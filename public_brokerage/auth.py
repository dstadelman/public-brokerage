"""
Authentication functions for the Public Brokerage API.
"""

import os
from typing import Optional

from .client import PublicBrokerageClient
from .models.auth import AccessTokenRequest, AccessTokenResponse


def create_access_token(
    secret: Optional[str] = None,
    validity_minutes: int = 15,
    client: Optional[PublicBrokerageClient] = None
) -> str:
    """
    Create a personal access token using a secret token.
    
    Args:
        secret: Personal secret token (if None, reads from environment)
        validity_minutes: Token validity in minutes (default: 15)
        client: Optional client instance to use
        
    Returns:
        Access token string
        
    Raises:
        ValueError: If secret token is not provided
        requests.exceptions.RequestException: For HTTP errors
    """
    if secret is None:
        secret = os.getenv("PUBLIC_SECRET_TOKEN")
        if not secret:
            raise ValueError(
                "Secret token is required. Provide it as parameter or set "
                "PUBLIC_SECRET_TOKEN environment variable."
            )
    
    # Use provided client or create a new one
    if client is None:
        client = PublicBrokerageClient()
    
    # Create request payload
    request_data = AccessTokenRequest(
        secret=secret,
        validityInMinutes=validity_minutes
    )
    
    # Make the API request
    response = client._make_request(
        method="POST",
        endpoint="/userapiauthservice/personal/access-tokens",
        data=request_data.model_dump(),
        include_auth=False  # This endpoint doesn't require auth
    )
    
    # Parse response
    token_response = client._handle_response(response, AccessTokenResponse)
    
    # Set the token on the client for future requests
    client.set_access_token(token_response.accessToken, validity_minutes)
    
    return token_response.accessToken


def ensure_access_token(client: PublicBrokerageClient) -> str:
    """
    Ensure the client has a valid access token, creating one if needed.
    
    Args:
        client: Client instance
        
    Returns:
        Valid access token
        
    Raises:
        ValueError: If secret token is not available
        requests.exceptions.RequestException: For HTTP errors
    """
    # Check if current token is valid
    if client.is_access_token_valid():
        return client.get_access_token()
    
    # Create new token
    if not client.secret_token:
        raise ValueError(
            "Secret token is required to create access token. "
            "Set it when creating the client or via PUBLIC_SECRET_TOKEN environment variable."
        )
    
    return create_access_token(
        secret=client.secret_token,
        client=client
    )
