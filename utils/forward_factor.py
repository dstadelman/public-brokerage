"""
Forward volatility and forward factor calculations.

This module provides functions for calculating:
- Forward variance from front and back leg IVs
- Forward volatility (annualized)
- Forward factor (FF) - the key metric for calendar spread trading
"""

import math
from typing import Optional


def calculate_forward_variance(
    front_iv: float,
    front_dte: int,
    back_iv: float,
    back_dte: int
) -> Optional[float]:
    """
    Calculate forward variance from front and back leg implied volatilities.
    
    Formula: ForwardVar = (σ₂²·T₂ - σ₁²·T₁) / (T₂ - T₁)
    
    Args:
        front_iv: Front leg implied volatility (annualized, e.g., 0.45 for 45%)
        front_dte: Front leg days to expiration
        back_iv: Back leg implied volatility (annualized, e.g., 0.38 for 38%)
        back_dte: Back leg days to expiration
        
    Returns:
        Forward variance (annualized), or None if calculation is invalid
    """
    if front_dte >= back_dte:
        # Front leg must expire before back leg
        return None
    
    if front_dte < 0 or back_dte < 0:
        return None
    
    if front_iv < 0 or back_iv < 0:
        return None
    
    # Convert DTE to years
    T1 = front_dte / 365.0
    T2 = back_dte / 365.0
    
    # Calculate forward variance
    numerator = (back_iv ** 2) * T2 - (front_iv ** 2) * T1
    denominator = T2 - T1
    
    if denominator == 0:
        return None
    
    forward_var = numerator / denominator
    
    # Allow negative variance (extreme backwardation) - floor to 0
    # Negative variance means front IV > back IV significantly
    # This is a tradeable signal (extreme backwardation/vol crush expected)
    if forward_var < 0:
        return 0.0
    
    return forward_var


def calculate_forward_vol(
    front_iv: float,
    front_dte: int,
    back_iv: float,
    back_dte: int
) -> Optional[float]:
    """
    Calculate forward volatility (annualized).
    
    Formula: ForwardVol = √(ForwardVariance)
    
    Args:
        front_iv: Front leg implied volatility (annualized)
        front_dte: Front leg days to expiration
        back_iv: Back leg implied volatility (annualized)
        back_dte: Back leg days to expiration
        
    Returns:
        Forward volatility (annualized), or None if calculation is invalid
    """
    forward_var = calculate_forward_variance(front_iv, front_dte, back_iv, back_dte)
    
    if forward_var is None:
        return None
    
    # forward_var can be 0 (floored from negative) - represents vol crush
    if forward_var == 0:
        return 0.0
    
    return math.sqrt(forward_var)


def calculate_forward_factor(
    front_iv: float,
    forward_vol: float
) -> Optional[float]:
    """
    Calculate forward factor (FF).
    
    Formula: FF = (Front IV - Forward Vol) / Forward Vol
    
    Interpretation:
    - FF > 0: Backwardation (front IV > forward vol) - favorable for calendar spreads
    - FF = 0: Flat (front IV = forward vol)
    - FF < 0: Contango (front IV < forward vol) - mean reversion signal
    
    Args:
        front_iv: Front leg implied volatility (annualized)
        forward_vol: Forward volatility (annualized)
        
    Returns:
        Forward factor (dimensionless), or None if calculation is invalid
    """
    if front_iv < 0:
        return None
    
    # Handle extreme backwardation: forward_vol = 0 means infinite FF
    # Return a large positive number to represent extreme backwardation
    if forward_vol == 0:
        if front_iv > 0:
            return float('inf')  # Infinite FF = extreme backwardation
        else:
            return 0.0  # Both zero = neutral
    
    ff = (front_iv - forward_vol) / forward_vol
    
    return ff


def calculate_forward_factor_from_ivs(
    front_iv: float,
    front_dte: int,
    back_iv: float,
    back_dte: int
) -> Optional[float]:
    """
    Calculate forward factor directly from front and back leg IVs.
    
    Convenience function that combines forward vol and FF calculation.
    
    Args:
        front_iv: Front leg implied volatility (annualized)
        front_dte: Front leg days to expiration
        back_iv: Back leg implied volatility (annualized)
        back_dte: Back leg days to expiration
        
    Returns:
        Forward factor (dimensionless), or None if calculation is invalid
    """
    forward_vol = calculate_forward_vol(front_iv, front_dte, back_iv, back_dte)
    
    if forward_vol is None:
        return None
    
    return calculate_forward_factor(front_iv, forward_vol)
