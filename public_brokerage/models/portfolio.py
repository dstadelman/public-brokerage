"""
Portfolio models for the Public Brokerage API.
"""

from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from .common import Instrument
from .account import AccountType
from .order import Order


class BuyingPower(BaseModel):
    """Buying power information."""
    cashOnlyBuyingPower: str
    buyingPower: str
    optionsBuyingPower: str


class Equity(BaseModel):
    """Equity breakdown."""
    type: str  # e.g., "CASH"
    value: str
    percentageOfPortfolio: str


class LastPrice(BaseModel):
    """Last price information."""
    lastPrice: str
    timestamp: datetime


class Gain(BaseModel):
    """Gain information."""
    gainValue: str
    gainPercentage: str
    timestamp: Optional[datetime] = None


class CostBasis(BaseModel):
    """Cost basis information."""
    totalCost: str
    unitCost: str
    gainValue: str
    gainPercentage: str
    lastUpdate: datetime


class Position(BaseModel):
    """Position model."""
    instrument: Instrument
    quantity: str
    openedAt: datetime
    currentValue: str
    percentOfPortfolio: str
    lastPrice: LastPrice
    instrumentGain: Gain
    positionDailyGain: Gain
    costBasis: CostBasis


class Portfolio(BaseModel):
    """Portfolio model."""
    accountId: str
    accountType: AccountType
    buyingPower: BuyingPower
    equity: List[Equity]
    positions: List[Position]
    orders: List[Order]

    class Config:
        """Pydantic configuration."""
        use_enum_values = True
