"""
Order state enumeration for Public.com brokerage API.

Based on industry standards and comprehensive analysis of order lifecycle states.
See ORDER_STATES.md for detailed documentation.
"""

from enum import Enum


class OrderState(Enum):
    """
    Enumeration of all possible order states in the Public.com brokerage API.
    
    Categories:
    - ACTIVE: Order is still working and may receive fills or state changes
    - TERMINAL: Order is complete and will not receive further fills
    """
    
    # ACTIVE STATES - Order still working
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    PENDING_REPLACE = "PENDING_REPLACE"
    PENDING_CANCEL = "PENDING_CANCEL"
    
    # TERMINAL STATES - Order complete
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    QUEUED_CANCELLED = "QUEUED_CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    REPLACED = "REPLACED"
    
    @classmethod
    def active_states(cls):
        """Get all active order states (order still working)."""
        return [cls.NEW, cls.PARTIALLY_FILLED, cls.PENDING_REPLACE, cls.PENDING_CANCEL]
    
    @classmethod
    def terminal_states(cls):
        """Get all terminal order states (order complete)."""
        return [cls.FILLED, cls.CANCELLED, cls.QUEUED_CANCELLED, cls.REJECTED, cls.EXPIRED, cls.REPLACED]
    
    @classmethod
    def cancelled_states(cls):
        """Get all states that indicate successful cancellation."""
        return [cls.CANCELLED, cls.QUEUED_CANCELLED, cls.REJECTED, cls.EXPIRED]
    
    @classmethod
    def fill_states(cls):
        """Get all states that indicate the order has fills."""
        return [cls.FILLED, cls.PARTIALLY_FILLED]
    
    def is_active(self) -> bool:
        """Check if this state indicates the order is still active."""
        return self in self.active_states()
    
    def is_terminal(self) -> bool:
        """Check if this state indicates the order is complete."""
        return self in self.terminal_states()
    
    def is_cancelled(self) -> bool:
        """Check if this state indicates successful cancellation."""
        return self in self.cancelled_states()
    
    def has_fills(self) -> bool:
        """Check if this state indicates the order has fills."""
        return self in self.fill_states()


# Convenience functions for string-based comparisons (for backward compatibility)
def is_active_state(status: str) -> bool:
    """Check if a status string represents an active order state."""
    try:
        state = OrderState(status)
        return state.is_active()
    except ValueError:
        # Handle unknown states - assume active for safety
        return True


def is_terminal_state(status: str) -> bool:
    """Check if a status string represents a terminal order state."""
    try:
        state = OrderState(status)
        return state.is_terminal()
    except ValueError:
        # Handle unknown states - assume not terminal for safety
        return False


def is_cancelled_state(status: str) -> bool:
    """Check if a status string represents a cancelled order state."""
    try:
        state = OrderState(status)
        return state.is_cancelled()
    except ValueError:
        # Handle unknown states - assume not cancelled for safety
        return False