"""
Account models for the Public Brokerage API.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from .common import TransactionType, TransactionDirection, OrderSide, InstrumentType


class AccountType(str, Enum):
    """Account type enumeration."""
    BROKERAGE = "BROKERAGE"
    HIGH_YIELD = "HIGH_YIELD"
    BOND_ACCOUNT = "BOND_ACCOUNT"
    RIA_ASSET = "RIA_ASSET"
    TREASURY = "TREASURY"
    TRADITIONAL_IRA = "TRADITIONAL_IRA"
    ROTH_IRA = "ROTH_IRA"


class OptionsLevel(str, Enum):
    """Options trading level."""
    NONE = "NONE"
    LEVEL_1 = "LEVEL_1"
    LEVEL_2 = "LEVEL_2"
    LEVEL_3 = "LEVEL_3"


class BrokerageAccountType(str, Enum):
    """Brokerage account type."""
    CASH = "CASH"
    MARGIN = "MARGIN"


class TradePermissions(str, Enum):
    """Trade permissions."""
    BUY_AND_SELL = "BUY_AND_SELL"
    LIQUIDATION_ONLY = "LIQUIDATION_ONLY"
    DISABLED = "DISABLED"


class Account(BaseModel):
    """Account information model."""
    accountId: str
    accountType: AccountType
    optionsLevel: OptionsLevel
    brokerageAccountType: BrokerageAccountType
    tradePermissions: TradePermissions

    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class AccountsResponse(BaseModel):
    """Response model for get accounts."""
    accounts: List[Account]


class Transaction(BaseModel):
    """Transaction model."""
    timestamp: datetime
    id: str
    type: TransactionType
    subType: str
    accountNumber: str
    symbol: Optional[str] = None
    securityType: Optional[InstrumentType] = None
    side: Optional[OrderSide] = None
    description: str
    netAmount: str
    principalAmount: str
    quantity: Optional[str] = None
    direction: TransactionDirection
    fees: str

    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class HistoryResponse(BaseModel):
    """Response model for account history."""
    transactions: List[Transaction]
    nextToken: Optional[str] = None
    start: datetime
    end: datetime
    pageSize: int
