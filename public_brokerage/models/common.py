"""
Common models and enums used across the Public Brokerage API.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class InstrumentType(str, Enum):
    """Types of financial instruments."""
    EQUITY = "EQUITY"
    OPTION = "OPTION"
    MULTI_LEG_INSTRUMENT = "MULTI_LEG_INSTRUMENT"
    CRYPTO = "CRYPTO"
    ALT = "ALT"
    TREASURY = "TREASURY"
    BOND = "BOND"
    INDEX = "INDEX"


class TradingStatus(str, Enum):
    """Trading permission status."""
    BUY_AND_SELL = "BUY_AND_SELL"
    LIQUIDATION_ONLY = "LIQUIDATION_ONLY"
    DISABLED = "DISABLED"


class OrderSide(str, Enum):
    """Order side: buy or sell."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    """Order status."""
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    QUEUED_CANCELLED = "QUEUED_CANCELLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    PENDING_REPLACE = "PENDING_REPLACE"
    PENDING_CANCEL = "PENDING_CANCEL"
    EXPIRED = "EXPIRED"
    REPLACED = "REPLACED"


class TimeInForce(str, Enum):
    """Time in force for orders."""
    DAY = "DAY"
    GTC = "GTC"  # Good Till Cancelled
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill


class OpenCloseIndicator(str, Enum):
    """Open/Close indicator for options."""
    OPEN = "OPEN"
    CLOSE = "CLOSE"


class OptionType(str, Enum):
    """Option type: call or put."""
    CALL = "CALL"
    PUT = "PUT"


class TransactionType(str, Enum):
    """Transaction type."""
    TRADE = "TRADE"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    DIVIDEND = "DIVIDEND"
    INTEREST = "INTEREST"
    FEE = "FEE"


class TransactionDirection(str, Enum):
    """Transaction direction."""
    INCOMING = "INCOMING"
    OUTGOING = "OUTGOING"


class QuoteOutcome(str, Enum):
    """Quote request outcome."""
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    UNKNOWN = "UNKNOWN"


class Instrument(BaseModel):
    """Financial instrument model."""
    symbol: str
    type: InstrumentType

    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class Expiration(BaseModel):
    """Order expiration settings."""
    timeInForce: TimeInForce
    expirationTime: Optional[datetime] = None

    class Config:
        """Pydantic configuration."""
        use_enum_values = True
