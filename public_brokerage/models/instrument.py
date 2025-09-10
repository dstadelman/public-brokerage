"""
Instrument models for the Public Brokerage API.
"""

from typing import List
from pydantic import BaseModel

from .common import Instrument, TradingStatus


class InstrumentWithTrading(BaseModel):
    """Instrument with trading status information."""
    instrument: Instrument
    trading: TradingStatus
    fractionalTrading: TradingStatus
    optionTrading: TradingStatus
    optionSpreadTrading: TradingStatus

    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class InstrumentsResponse(BaseModel):
    """Response model for get all instruments."""
    instruments: List[InstrumentWithTrading]
