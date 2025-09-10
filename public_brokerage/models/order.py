"""
Order models for the Public Brokerage API.
"""

from typing import List, Optional
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
    """Order request model."""
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


class MultiLegOrderRequest(BaseModel):
    """Multi-leg order request model."""
    orderId: str  # UUID string
    quantity: int
    type: OrderType  # Only LIMIT allowed
    limitPrice: str
    expiration: Expiration
    legs: List[OrderLeg]

    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class OrderResponse(BaseModel):
    """Order response model."""
    orderId: str


class RegulatoryFees(BaseModel):
    """Regulatory fees model."""
    secFee: str
    tafFee: str
    orfFee: str
    exchangeFee: str
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
    cusip: str
    rootSymbol: str
    rootOptionSymbol: str
    estimatedCommission: str
    regulatoryFees: RegulatoryFees
    estimatedIndexOptionFee: str
    orderValue: str
    estimatedQuantity: str
    estimatedCost: str
    buyingPowerRequirement: str
    estimatedProceeds: str
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
    estimatedIndexOptionFee: str
    orderValue: str
    estimatedQuantity: str
    estimatedCost: str
    buyingPowerRequirement: str
    estimatedProceeds: str
    marginRequirement: Optional[MarginRequirement] = None
    marginImpact: Optional[MarginImpact] = None
    priceIncrement: Optional[PriceIncrement] = None
