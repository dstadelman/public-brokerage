"""
Market data models for the Public Brokerage API.
"""

from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, date

from .common import Instrument, QuoteOutcome


class QuotesRequest(BaseModel):
    """Request model for getting quotes."""
    instruments: List[Instrument]


class Quote(BaseModel):
    """Quote model."""
    instrument: Instrument
    outcome: QuoteOutcome
    last: Optional[str] = None
    lastTimestamp: Optional[datetime] = None
    bid: Optional[str] = None
    bidSize: Optional[int] = None
    bidTimestamp: Optional[datetime] = None
    ask: Optional[str] = None
    askSize: Optional[int] = None
    askTimestamp: Optional[datetime] = None
    volume: Optional[int] = None
    openInterest: Optional[int] = None

    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class QuotesResponse(BaseModel):
    """Response model for quotes."""
    quotes: List[Quote]


class OptionExpirationsRequest(BaseModel):
    """Request model for option expirations."""
    instrument: Instrument


class OptionExpirationsResponse(BaseModel):
    """Response model for option expirations."""
    baseSymbol: str
    expirations: List[date]


class OptionChainRequest(BaseModel):
    """Request model for option chain."""
    instrument: Instrument
    expirationDate: date


class OptionChainResponse(BaseModel):
    """Response model for option chain."""
    baseSymbol: str
    calls: List[Quote]
    puts: List[Quote]


class OptionGreeks(BaseModel):
    """Option Greeks model."""
    delta: str
    gamma: str
    theta: str
    vega: str
    rho: str
    impliedVolatility: str
