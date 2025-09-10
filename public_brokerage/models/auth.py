"""
Authentication models for the Public Brokerage API.
"""

from pydantic import BaseModel


class AccessTokenRequest(BaseModel):
    """Request model for creating an access token."""
    secret: str
    validityInMinutes: int = 15


class AccessTokenResponse(BaseModel):
    """Response model for access token creation."""
    accessToken: str
