"""
Order models for the Public Brokerage API.
"""

from typing import List, Optional, Union
from pydantic import BaseModel
from datetime import datetime, date
from uuid import UUID

from .common import (
    Instrument, OrderSide, OrderType, OrderStatus, 
    Expiration, OpenCloseIndicator, OptionType
)


class OptionDetails(BaseModel):
    """Option details model."""
    baseSymbol: str
    type: OptionType
    strikePrice: str
    optionExpireDate: date

    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class OrderLeg(BaseModel):
    """Order leg model for multi-leg orders."""
    instrument: Instrument
    side: OrderSide
    openCloseIndicator: OpenCloseIndicator
    ratioQuantity: int
    optionDetails: Optional[OptionDetails] = None

    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class Order(BaseModel):
    """Order model."""
    orderId: str
    instrument: Instrument
    createdAt: datetime
    type: OrderType
    side: OrderSide
    status: OrderStatus
    quantity: Optional[str] = None
    notionalValue: Optional[str] = None
    expiration: Expiration
    limitPrice: Optional[str] = None
    stopPrice: Optional[str] = None
    closedAt: Optional[datetime] = None
    openCloseIndicator: Optional[OpenCloseIndicator] = None
    filledQuantity: Optional[str] = None
    averagePrice: Optional[str] = None
    legs: Optional[List[OrderLeg]] = None
    rejectReason: Optional[str] = None

    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class OrderRequest(BaseModel):
    """Order request model (for actual order placement)."""
    orderId: str  # UUID string
    instrument: Instrument
    orderSide: OrderSide
    orderType: OrderType
    expiration: Expiration
    quantity: Optional[str] = None
    amount: Optional[str] = None
    limitPrice: Optional[str] = None
    stopPrice: Optional[str] = None
    openCloseIndicator: Optional[OpenCloseIndicator] = None

    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class SingleLegPreflightRequest(BaseModel):
    """Single-leg preflight request model."""
    instrument: Instrument
    orderSide: OrderSide
    orderType: OrderType
    expiration: Expiration
    quantity: str
    limitPrice: Optional[str] = None
    stopPrice: Optional[str] = None
    openCloseIndicator: Optional[OpenCloseIndicator] = None

    class Config:
        """Pydantic configuration."""
        use_enum_values = True
        exclude_none = True


class MultiLegPreflightRequest(BaseModel):
    """Multi-leg preflight request model."""
    orderType: OrderType  # Uses orderType for preflight
    quantity: str  # String for preflight
    limitPrice: str
    expiration: Expiration
    legs: List[OrderLeg]

    class Config:
        """Pydantic configuration."""
        use_enum_values = True
        exclude_none = True


class MultiLegOrderRequest(BaseModel):
    """Multi-leg order request model."""
    orderId: str  # Required for actual orders
    quantity: int  # int for actual orders
    type: OrderType  # Uses type for actual orders
    limitPrice: str
    expiration: Expiration
    legs: List[OrderLeg]

    class Config:
        """Pydantic configuration."""
        use_enum_values = True
        exclude_none = True


class OrderResponse(BaseModel):
    """Order response model."""
    orderId: str


class RegulatoryFees(BaseModel):
    """Regulatory fees model."""
    secFee: str
    tafFee: str
    orfFee: str
    exchangeFee: Optional[str] = None
    occFee: str
    catFee: str


class EstimatedOrderRebate(BaseModel):
    """Estimated order rebate model."""
    estimatedOptionRebate: str
    optionRebatePercent: int
    perContractRebate: str


class MarginRequirement(BaseModel):
    """Margin requirement model."""
    longMaintenanceRequirement: str
    longInitialRequirement: str


class MarginImpact(BaseModel):
    """Margin impact model."""
    marginUsageImpact: str
    initialMarginRequirement: str


class PriceIncrement(BaseModel):
    """Price increment model."""
    incrementBelow3: str
    incrementAbove3: str
    currentIncrement: str


class PreflightResponse(BaseModel):
    """Preflight response model."""
    instrument: Instrument
    cusip: Optional[str] = None
    rootSymbol: str
    rootOptionSymbol: str
    estimatedCommission: Optional[str] = None
    regulatoryFees: RegulatoryFees
    estimatedIndexOptionFee: Optional[str] = None
    orderValue: str
    estimatedQuantity: str
    estimatedCost: Optional[str] = None  # Can be null for certain order types
    buyingPowerRequirement: Optional[str] = None  # Can be null for certain order types
    estimatedProceeds: Optional[str] = None
    optionDetails: Optional[OptionDetails] = None
    estimatedOrderRebate: Optional[EstimatedOrderRebate] = None
    marginRequirement: Optional[MarginRequirement] = None
    marginImpact: Optional[MarginImpact] = None
    priceIncrement: Optional[PriceIncrement] = None


class MultiLegPreflightResponse(BaseModel):
    """Multi-leg preflight response model."""
    baseSymbol: str
    strategyName: str
    legs: List[OrderLeg]
    estimatedCommission: str
    regulatoryFees: RegulatoryFees
    estimatedIndexOptionFee: Optional[str] = None
    orderValue: str
    estimatedQuantity: str
    estimatedCost: str
    buyingPowerRequirement: str
    estimatedProceeds: Optional[str] = None
    marginRequirement: Optional[MarginRequirement] = None
    marginImpact: Optional[MarginImpact] = None
    priceIncrement: Optional[PriceIncrement] = None
