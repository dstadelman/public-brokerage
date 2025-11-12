"""
Black-Scholes-Merton option pricing and implied volatility estimation.

This module provides functions for:
- Theoretical option pricing using Black-Scholes-Merton model
- Implied volatility (IV) estimation from market prices using Newton-Raphson
- Vega calculation for IV convergence
"""

import math
from typing import Optional
from scipy.stats import norm


def black_scholes_call(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    q: float = 0.0
) -> float:
    """
    Calculate theoretical call option price using Black-Scholes-Merton model.
    
    Args:
        S: Current underlying price
        K: Strike price
        T: Time to expiration in years
        r: Risk-free interest rate (annualized)
        sigma: Volatility (annualized)
        q: Dividend yield (annualized), default 0.0
        
    Returns:
        Theoretical call option price
    """
    if T <= 0:
        # At or past expiration, return intrinsic value
        return max(0, S - K)
    
    if sigma <= 0:
        # Zero volatility case
        if S > K:
            return S * math.exp(-q * T) - K * math.exp(-r * T)
        else:
            return 0.0
    
    # Calculate d1 and d2
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    
    # Calculate call price
    call_price = (
        S * math.exp(-q * T) * norm.cdf(d1) - 
        K * math.exp(-r * T) * norm.cdf(d2)
    )
    
    return call_price


def black_scholes_put(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    q: float = 0.0
) -> float:
    """
    Calculate theoretical put option price using Black-Scholes-Merton model.
    
    Args:
        S: Current underlying price
        K: Strike price
        T: Time to expiration in years
        r: Risk-free interest rate (annualized)
        sigma: Volatility (annualized)
        q: Dividend yield (annualized), default 0.0
        
    Returns:
        Theoretical put option price
    """
    if T <= 0:
        # At or past expiration, return intrinsic value
        return max(0, K - S)
    
    if sigma <= 0:
        # Zero volatility case
        if K > S:
            return K * math.exp(-r * T) - S * math.exp(-q * T)
        else:
            return 0.0
    
    # Calculate d1 and d2
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    
    # Calculate put price
    put_price = (
        K * math.exp(-r * T) * norm.cdf(-d2) - 
        S * math.exp(-q * T) * norm.cdf(-d1)
    )
    
    return put_price


def vega(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    q: float = 0.0
) -> float:
    """
    Calculate vega (derivative of option price with respect to volatility).
    
    Used for Newton-Raphson IV estimation convergence.
    
    Args:
        S: Current underlying price
        K: Strike price
        T: Time to expiration in years
        r: Risk-free interest rate (annualized)
        sigma: Volatility (annualized)
        q: Dividend yield (annualized), default 0.0
        
    Returns:
        Vega value
    """
    if T <= 0 or sigma <= 0:
        return 0.0
    
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    
    # Vega = S * exp(-q*T) * phi(d1) * sqrt(T)
    # where phi is the standard normal probability density function
    vega_value = S * math.exp(-q * T) * norm.pdf(d1) * math.sqrt(T)
    
    return vega_value


def estimate_iv_from_price(
    option_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    q: float = 0.0,
    option_type: str = 'call',
    initial_guess: float = 0.3,
    tolerance: float = 1e-5,
    max_iterations: int = 100
) -> Optional[float]:
    """
    Estimate implied volatility from market option price using Newton-Raphson method.
    
    Args:
        option_price: Market price of the option
        S: Current underlying price
        K: Strike price
        T: Time to expiration in years
        r: Risk-free interest rate (annualized)
        q: Dividend yield (annualized), default 0.0
        option_type: 'call' or 'put', default 'call'
        initial_guess: Starting volatility guess, default 0.3 (30%)
        tolerance: Convergence tolerance, default 1e-5
        max_iterations: Maximum Newton-Raphson iterations, default 100
        
    Returns:
        Implied volatility (annualized), or None if cannot be solved
    """
    is_call = option_type.lower() in ['call', 'c']
    
    # Check for intrinsic value violations
    if is_call:
        intrinsic_value = max(0, S * math.exp(-q * T) - K * math.exp(-r * T))
    else:
        intrinsic_value = max(0, K * math.exp(-r * T) - S * math.exp(-q * T))
    
    if option_price < intrinsic_value - tolerance:
        # Price below intrinsic value - arbitrage violation
        return None
    
    if option_price <= 0:
        return None
    
    if T <= 0:
        # At or past expiration
        return None
    
    # Newton-Raphson iteration
    sigma = initial_guess
    
    for i in range(max_iterations):
        # Calculate theoretical price and vega at current sigma
        if is_call:
            theo_price = black_scholes_call(S, K, T, r, sigma, q)
        else:
            theo_price = black_scholes_put(S, K, T, r, sigma, q)
        
        vega_value = vega(S, K, T, r, sigma, q)
        
        # Check if vega is too small (can't converge)
        if abs(vega_value) < 1e-10:
            return None
        
        # Calculate price difference
        price_diff = theo_price - option_price
        
        # Check for convergence
        if abs(price_diff) < tolerance:
            return sigma
        
        # Newton-Raphson update: sigma_new = sigma_old - f(sigma)/f'(sigma)
        sigma = sigma - price_diff / vega_value
        
        # Keep sigma in reasonable bounds
        if sigma <= 0.001:  # 0.1% minimum
            sigma = 0.001
        elif sigma > 10.0:  # 1000% maximum
            sigma = 10.0
    
    # Did not converge within max iterations
    # If we're close enough, return the last estimate
    if is_call:
        final_price = black_scholes_call(S, K, T, r, sigma, q)
    else:
        final_price = black_scholes_put(S, K, T, r, sigma, q)
    
    if abs(final_price - option_price) < tolerance * 10:
        return sigma
    
    return None
