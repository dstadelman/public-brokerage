"""
Option symbol utilities for OSI-compliant option symbol formatting.

The Option Symbology Initiative (OSI) provides a standardized 21-character naming 
convention for option contracts. This module implements the proper formatting 
according to OSI standards.

OSI Format: [Underlying_Symbol][Expiration_Date][Call/Put_Indicator][Strike_Price]
Example: MSFT251219C00275000

Components:
- Underlying Symbol: Up to 6 characters, padded with spaces if necessary
- Expiration Date: 6 digits (yymmdd)
- Call/Put Indicator: Single letter (C or P)
- Strike Price: 8 digits, front-padded with zeros, representing price in mills
"""

from datetime import datetime
from typing import Literal


def format_osi_symbol(
    underlying: str,
    expiration_date: str,
    option_type: Literal["C", "P", "CALL", "PUT"],
    strike_price: float,
    pad_underlying: bool = False
) -> str:
    """
    Format an option symbol according to OSI standards.
    
    Args:
        underlying: The underlying stock/ETF symbol (up to 6 characters)
        expiration_date: Expiration date in YYYY-MM-DD format
        option_type: Option type - "C"/"CALL" for calls, "P"/"PUT" for puts
        strike_price: Strike price as a float (e.g., 275.50)
        pad_underlying: Whether to pad underlying to 6 characters (False for condensed/API format, True for strict OSI)
        
    Returns:
        OSI-compliant option symbol (condensed format by default)
        
    Example:
        >>> format_osi_symbol("MSFT", "2025-12-19", "C", 275.00)
        'MSFT251219C00275000'
        
        >>> format_osi_symbol("MSFT", "2025-12-19", "C", 275.00, pad_underlying=True)
        'MSFT  251219C00275000'
        
        >>> format_osi_symbol("SPY", "2025-01-17", "P", 450.50)
        'SPY250117P00450500'
    """
    # Validate inputs
    if len(underlying) > 6:
        raise ValueError(f"Underlying symbol '{underlying}' exceeds 6 characters")
    
    # Format underlying symbol (pad to 6 characters with spaces if requested)
    if pad_underlying:
        underlying_formatted = underlying.ljust(6)
    else:
        underlying_formatted = underlying
    
    # Format expiration date (yymmdd)
    try:
        exp_date = datetime.strptime(expiration_date, '%Y-%m-%d')
        exp_formatted = exp_date.strftime('%y%m%d')
    except ValueError:
        raise ValueError(f"Invalid expiration date format '{expiration_date}'. Use YYYY-MM-DD")
    
    # Format option type indicator
    option_type_upper = option_type.upper()
    if option_type_upper in ["C", "CALL"]:
        type_indicator = "C"
    elif option_type_upper in ["P", "PUT"]:
        type_indicator = "P"
    else:
        raise ValueError(f"Invalid option type '{option_type}'. Use 'C', 'CALL', 'P', or 'PUT'")
    
    # Format strike price (8 digits, representing price in mills)
    # Strike price is multiplied by 1000 to convert to mills, then padded to 8 digits
    if strike_price < 0:
        raise ValueError(f"Strike price cannot be negative: {strike_price}")
    
    strike_mills = int(round(strike_price * 1000))
    if strike_mills > 99999999:  # 8-digit limit
        raise ValueError(f"Strike price {strike_price} too large for OSI format")
    
    strike_formatted = f"{strike_mills:08d}"
    
    # Construct the full OSI symbol
    osi_symbol = f"{underlying_formatted}{exp_formatted}{type_indicator}{strike_formatted}"
    
    # Validate final length only if padding is enabled
    if pad_underlying and len(osi_symbol) != 21:
        raise ValueError(f"Generated symbol '{osi_symbol}' is not 21 characters (got {len(osi_symbol)})")
    
    return osi_symbol


def parse_osi_symbol(osi_symbol: str) -> dict:
    """
    Parse an OSI-compliant option symbol into its components.
    Supports both standard 21-character format and condensed format.
    
    Args:
        osi_symbol: OSI option symbol (21-character padded or condensed format)
        
    Returns:
        Dictionary with keys: underlying, expiration_date, option_type, strike_price
        
    Example:
        >>> parse_osi_symbol("MSFT  251219C00275000")  # 21-character format
        {
            'underlying': 'MSFT',
            'expiration_date': '2025-12-19',
            'option_type': 'C',
            'strike_price': 275.0
        }
        
        >>> parse_osi_symbol("MSFT251219C00275000")  # Condensed format
        {
            'underlying': 'MSFT',
            'expiration_date': '2025-12-19',
            'option_type': 'C',
            'strike_price': 275.0
        }
    """
    # Find the last C or P in the symbol to locate option type
    call_pos = osi_symbol.rfind('C')
    put_pos = osi_symbol.rfind('P')
    
    if call_pos == -1 and put_pos == -1:
        raise ValueError(f"No option type indicator (C or P) found in symbol: {osi_symbol}")
    
    # Get position of the option type indicator
    type_pos = max(call_pos, put_pos)
    option_type = osi_symbol[type_pos]
    
    # Extract components based on positions relative to option type
    # The date is 6 characters before the option type
    date_start_pos = type_pos - 6
    if date_start_pos < 1:
        raise ValueError(f"Invalid symbol format - insufficient characters before option type: {osi_symbol}")
        
    underlying = osi_symbol[:date_start_pos].rstrip()  # Remove trailing spaces
    exp_str = osi_symbol[date_start_pos:type_pos]
    
    # Strike is 8 characters after option type
    if len(osi_symbol) < type_pos + 9:
        raise ValueError(f"Invalid symbol format - insufficient characters for strike price: {osi_symbol}")
        
    strike_str = osi_symbol[type_pos + 1:type_pos + 9]
    
    # Parse expiration date
    try:
        exp_date = datetime.strptime(exp_str, '%y%m%d')
        expiration_date = exp_date.strftime('%Y-%m-%d')
    except ValueError:
        raise ValueError(f"Invalid expiration date in symbol: {exp_str}")
    
    # Validate option type
    if option_type not in ['C', 'P']:
        raise ValueError(f"Invalid option type indicator: {option_type}")
    
    # Parse strike price (convert from mills back to dollars)
    try:
        strike_mills = int(strike_str)
        strike_price = strike_mills / 1000.0
    except ValueError:
        raise ValueError(f"Invalid strike price in symbol: {strike_str}")
    
    return {
        'underlying': underlying,
        'expiration_date': expiration_date,
        'option_type': option_type,
        'strike_price': strike_price
    }


def validate_osi_symbol(osi_symbol: str) -> bool:
    """
    Validate if a string is a properly formatted OSI symbol.
    
    Args:
        osi_symbol: String to validate
        
    Returns:
        True if valid OSI symbol, False otherwise
    """
    try:
        parse_osi_symbol(osi_symbol)
        return True
    except ValueError:
        return False
