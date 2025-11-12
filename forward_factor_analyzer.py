"""
Forward Factor Analyzer for calendar spread trading.

This module provides analysis and calculation functions for forward factor-based
calendar spread strategies, including:
- Calculating FF at a given spread price
- Solving for spread price at a target FF
- Analyzing existing positions for FF
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from scipy.optimize import brentq

from public_brokerage.client import PublicBrokerageClient
from public_brokerage.market_data import get_quotes, get_option_chain
from public_brokerage.models.common import Instrument, InstrumentType
from utils.black_scholes import black_scholes_call, estimate_iv_from_price
from utils.forward_factor import calculate_forward_factor_from_ivs
from config import config

logger = logging.getLogger(__name__)


class ForwardFactorAnalyzer:
    """
    Analyzer for forward factor-based calendar spread trading.
    
    Key functions:
    1. Calculate FF at a specific spread price (spread_price → FF)
    2. Solve for spread price at target FF (target_ff → spread_price)
    3. Analyze existing positions for current FF
    """
    
    def __init__(self, client: PublicBrokerageClient, account_id: Optional[str] = None):
        """
        Initialize the forward factor analyzer.
        
        Args:
            client: Authenticated PublicBrokerageClient instance
            account_id: Account ID (required for market data calls)
        """
        self.client = client
        self.account_id = account_id
    
    def calculate_ff_at_spread_price(
        self,
        spread_price: float,
        underlying_price: float,
        short_exp: str,
        long_exp: str,
        strike: float,
        option_chain_short: Dict,
        option_chain_long: Dict,
        risk_free_rate: Optional[float] = None
    ) -> Optional[float]:
        """
        Calculate forward factor at a given spread price.
        
        Given a spread price, derive individual leg prices (based on current
        market ratio), calculate IV for each leg, then compute FF.
        
        This is the key function that maps: spread_price → FF
        
        Args:
            spread_price: Target spread price (debit)
            underlying_price: Current underlying price
            short_exp: Short leg expiration date (YYYY-MM-DD)
            long_exp: Long leg expiration date (YYYY-MM-DD)
            strike: Strike price for both legs
            option_chain_short: Option chain data for short leg
            option_chain_long: Option chain data for long leg
            risk_free_rate: Risk-free rate (uses config default if None)
            
        Returns:
            Forward factor at this spread price, or None if cannot calculate
        """
        if risk_free_rate is None:
            risk_free_rate = config.get_ff_risk_free_rate()
        
        # Find the specific options in the chain
        short_option = self._find_option_in_chain(option_chain_short, strike)
        long_option = self._find_option_in_chain(option_chain_long, strike)
        
        if not short_option or not long_option:
            logger.error(f"Could not find strike {strike} in option chains")
            return None
        
        # Get current MID prices to establish the ratio
        short_mid = (short_option['bid'] + short_option['ask']) / 2
        long_mid = (long_option['bid'] + long_option['ask']) / 2
        current_spread_mid = long_mid - short_mid
        
        # Decompose the given spread_price into individual option prices
        # using the current market ratio between legs
        # 
        # For calendar: spread = long - short
        # At current market: spread_mid = long_mid - short_mid
        # Ratio: long_mid / short_mid (how much more expensive the long leg is)
        
        if short_mid < 0.01:
            logger.warning(f"Short option price too low ({short_mid:.2f}) for ratio calculation")
            return None
        
        ratio = long_mid / short_mid if short_mid > 0 else 1.0
        
        # Given a target spread_price, solve for individual prices:
        # spread_price = long_price - short_price
        # long_price = ratio * short_price
        # => spread_price = (ratio * short_price) - short_price
        # => spread_price = short_price * (ratio - 1)
        # => short_price = spread_price / (ratio - 1)
        
        if abs(ratio - 1.0) < 0.01:
            # Legs are nearly equal in price - use 50/50 split
            short_price = spread_price / 2 if spread_price > 0 else short_mid
            long_price = short_price + spread_price
        else:
            short_price = spread_price / (ratio - 1) if ratio > 1 else short_mid
            long_price = short_price + spread_price
        
        # Validate prices are reasonable
        if short_price < 0.005 or long_price < 0.005:
            logger.warning(f"Derived prices too low for IV calculation (short=${short_price:.2f}, long=${long_price:.2f})")
            return None
        
        # Calculate DTEs
        short_dte = self._calculate_dte(short_exp)
        long_dte = self._calculate_dte(long_exp)
        
        if short_dte is None or long_dte is None or short_dte >= long_dte:
            logger.error(f"Invalid DTEs: short={short_dte}, long={long_dte}")
            return None
        
        # Calculate time to expiration in years
        short_T = short_dte / 365.0
        long_T = long_dte / 365.0
        
        # Calculate ATF drift for each expiration (market-implied interest rate)
        short_atf_rate = self.calculate_atf_drift(underlying_price, option_chain_short, short_exp, short_dte)
        long_atf_rate = self.calculate_atf_drift(underlying_price, option_chain_long, long_exp, long_dte)
        
        # Estimate IV from prices using Black-Scholes with ATF rates
        short_iv = estimate_iv_from_price(
            option_price=short_price,
            S=underlying_price,
            K=strike,
            T=short_T,
            r=short_atf_rate,  # Use ATF drift instead of static risk-free rate
            q=0.0
        )
        
        long_iv = estimate_iv_from_price(
            option_price=long_price,
            S=underlying_price,
            K=strike,
            T=long_T,
            r=long_atf_rate,  # Use ATF drift instead of static risk-free rate
            q=0.0
        )
        
        if short_iv is None or long_iv is None:
            logger.error(f"Could not estimate IV: short_iv={short_iv}, long_iv={long_iv}")
            return None
        
        # Calculate forward factor
        ff = calculate_forward_factor_from_ivs(
            front_iv=short_iv,
            front_dte=short_dte,
            back_iv=long_iv,
            back_dte=long_dte
        )
        
        return ff
    
    def solve_for_spread_price_at_ff(
        self,
        target_ff: float,
        underlying_price: float,
        short_exp: str,
        long_exp: str,
        strike: float,
        option_chain_short: Dict,
        option_chain_long: Dict,
        current_spread_mid: float,
        risk_free_rate: Optional[float] = None
    ) -> Optional[float]:
        """
        Solve for spread price that gives exactly target_ff.
        
        Uses numerical solver (scipy.optimize.brentq) to find the spread price
        where calculate_ff_at_spread_price() == target_ff.
        
        This is the inverse function: target_ff → spread_price
        
        Args:
            target_ff: Target forward factor (e.g., 0.2 for 20% backwardation)
            underlying_price: Current underlying price
            short_exp: Short leg expiration date (YYYY-MM-DD)
            long_exp: Long leg expiration date (YYYY-MM-DD)
            strike: Strike price for both legs
            option_chain_short: Option chain data for short leg
            option_chain_long: Option chain data for long leg
            current_spread_mid: Current market spread MID price
            risk_free_rate: Risk-free rate (uses config default if None)
            
        Returns:
            Spread price that achieves target_ff, or None if cannot solve
        """
        if risk_free_rate is None:
            risk_free_rate = config.get_ff_risk_free_rate()
        
        # Define the function to find root of: f(price) = FF(price) - target_ff
        def ff_diff(spread_price: float) -> float:
            ff = self.calculate_ff_at_spread_price(
                spread_price=spread_price,
                underlying_price=underlying_price,
                short_exp=short_exp,
                long_exp=long_exp,
                strike=strike,
                option_chain_short=option_chain_short,
                option_chain_long=option_chain_long,
                risk_free_rate=risk_free_rate
            )
            if ff is None:
                return float('inf')  # Return large value if can't calculate
            return ff - target_ff
        
        # Set search bounds
        # Lower bound: very small spread (near 0)
        # Upper bound: much larger than current spread
        lower_bound = 0.01
        upper_bound = max(current_spread_mid * 3.0, 10.0)
        
        try:
            # Use Brent's method for root finding
            solution = brentq(
                f=ff_diff,
                a=lower_bound,
                b=upper_bound,
                xtol=0.01,  # Tolerance of $0.01
                maxiter=100
            )
            return solution
        except ValueError as e:
            logger.error(f"Solver failed to converge: {e}")
            logger.error(f"Target FF: {target_ff}, Current spread MID: {current_spread_mid}")
            logger.error(f"FF at lower bound ({lower_bound}): {ff_diff(lower_bound) + target_ff}")
            logger.error(f"FF at upper bound ({upper_bound}): {ff_diff(upper_bound) + target_ff}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in solver: {e}")
            return None
    
    def analyze_calendar_spread_for_reporting(
        self,
        symbol: str,
        short_exp: str,
        long_exp: str,
        strike: float,
        risk_free_rate: Optional[float] = None
    ) -> Optional[Dict]:
        """
        Analyze a calendar spread for positions display (uses MID prices).
        
        Fetches option chain data, calculates IVs from MID prices,
        computes forward vol and FF.
        
        Args:
            symbol: Underlying symbol
            short_exp: Short leg expiration date (YYYY-MM-DD)
            long_exp: Long leg expiration date (YYYY-MM-DD)
            strike: Strike price for both legs
            risk_free_rate: Risk-free rate (uses config default if None)
            
        Returns:
            Dict with FF analysis metrics, or None if cannot calculate
        """
        if risk_free_rate is None:
            risk_free_rate = config.get_ff_risk_free_rate()
        
        try:
            if not self.account_id:
                logger.error("Account ID required for market data")
                return None
            
            # Fetch option chains
            from datetime import datetime
            short_date = datetime.strptime(short_exp, "%Y-%m-%d").date()
            long_date = datetime.strptime(long_exp, "%Y-%m-%d").date()
            
            instrument = Instrument(symbol=symbol, type=InstrumentType.EQUITY)
            short_chain = get_option_chain(self.client, self.account_id, instrument, short_date)
            long_chain = get_option_chain(self.client, self.account_id, instrument, long_date)
            
            # Get underlying price
            quotes = get_quotes(self.client, self.account_id, [instrument])
            if not quotes or len(quotes) == 0:
                logger.error(f"No quote found for {symbol}")
                return None
            underlying_price = float(quotes[0].last) if quotes[0].last else None
            if not underlying_price:
                logger.error(f"Invalid quote for {symbol}")
                return None
            
            # Find specific options
            short_option = self._find_option_in_chain(short_chain, strike)
            long_option = self._find_option_in_chain(long_chain, strike)
            
            if not short_option or not long_option:
                return None
            
            # Calculate MID prices
            short_mid = (short_option['bid'] + short_option['ask']) / 2
            long_mid = (long_option['bid'] + long_option['ask']) / 2
            spread_mid = long_mid - short_mid
            
            # Calculate DTEs
            short_dte = self._calculate_dte(short_exp)
            long_dte = self._calculate_dte(long_exp)
            
            if short_dte is None or long_dte is None:
                return None
            
            # Calculate IVs from MID prices using ATF rates
            short_T = short_dte / 365.0
            long_T = long_dte / 365.0
            
            # Calculate ATF drift for each expiration
            short_atf_rate = self.calculate_atf_drift(underlying_price, short_chain, short_exp, short_dte)
            long_atf_rate = self.calculate_atf_drift(underlying_price, long_chain, long_exp, long_dte)
            
            short_iv = estimate_iv_from_price(
                option_price=short_mid,
                S=underlying_price,
                K=strike,
                T=short_T,
                r=short_atf_rate,  # Use ATF drift
                q=0.0
            )
            
            long_iv = estimate_iv_from_price(
                option_price=long_mid,
                S=underlying_price,
                K=strike,
                T=long_T,
                r=long_atf_rate,  # Use ATF drift
                q=0.0
            )
            
            if short_iv is None or long_iv is None:
                return None
            
            # Calculate FF
            ff = calculate_forward_factor_from_ivs(
                front_iv=short_iv,
                front_dte=short_dte,
                back_iv=long_iv,
                back_dte=long_dte
            )
            
            if ff is None:
                return None
            
            return {
                'symbol': symbol,
                'strike': strike,
                'short_exp': short_exp,
                'long_exp': long_exp,
                'short_dte': short_dte,
                'long_dte': long_dte,
                'underlying_price': underlying_price,
                'short_mid': short_mid,
                'long_mid': long_mid,
                'spread_mid': spread_mid,
                'spread_bid': long_option['bid'] - short_option['ask'],
                'spread_ask': long_option['ask'] - short_option['bid'],
                'short_iv': short_iv,
                'long_iv': long_iv,
                'forward_factor': ff,
                'short_atf_rate': short_atf_rate,
                'long_atf_rate': long_atf_rate
            }
            
        except Exception as e:
            logger.error(f"Error analyzing calendar spread: {e}")
            return None
    
    def _find_option_in_chain(self, chain, strike: float) -> Optional[Dict]:
        """
        Find a specific strike in an option chain.
        
        Args:
            chain: OptionChainResponse object
            strike: Strike price to find
            
        Returns:
            Option data dict with pricing (IV will be calculated later), or None if not found
        """
        # Check if chain has calls (OptionChainResponse object)
        if hasattr(chain, 'calls'):
            for option in chain.calls:
                # Extract strike from OSI symbol
                try:
                    # OSI format: SYMBOL[spaces]YYMMDD[C/P]PPPPPSSS
                    # Example: SPY   250117C00500000
                    symbol_str = option.instrument.symbol
                    # Find where the date starts (6 digits)
                    date_start = len(symbol_str) - 15  # 6 (date) + 1 (C/P) + 8 (price)
                    option_strike_str = symbol_str[-8:]  # Last 8 digits are price * 1000
                    option_strike = float(option_strike_str) / 1000.0
                    
                    if abs(option_strike - strike) < 0.01:  # Float comparison tolerance
                        # Convert Quote object to dict format
                        # Note: IV is NOT included here - it will be calculated from price
                        return {
                            'symbol': symbol_str,
                            'strike': option_strike,
                            'bid': float(option.bid) if option.bid else 0.0,
                            'ask': float(option.ask) if option.ask else 0.0,
                            'last': float(option.last) if option.last else 0.0
                        }
                except (ValueError, AttributeError, IndexError) as e:
                    logger.warning(f"Could not parse option symbol: {e}")
                    continue
        return None
    
    def _calculate_dte(self, exp_date_str: str) -> Optional[int]:
        """
        Calculate days to expiration from date string.
        
        Args:
            exp_date_str: Expiration date in YYYY-MM-DD format
            
        Returns:
            Days to expiration, or None if invalid
        """
        try:
            exp_date = datetime.strptime(exp_date_str, "%Y-%m-%d").date()
            today = datetime.now().date()
            dte = (exp_date - today).days
            return max(0, dte)  # Don't return negative
        except Exception as e:
            logger.error(f"Error calculating DTE from {exp_date_str}: {e}")
            return None
    
    def calculate_atf_drift(
        self,
        underlying_price: float,
        option_chain: Dict,
        exp_date_str: str,
        dte: int
    ) -> float:
        """
        Calculate At-The-Forward (ATF) drift from options market.
        
        ATF is where Call(K) - Put(K) = 0, revealing the market's implied forward price.
        We find the strike where call and put values are closest, interpolate if needed,
        then calculate the annualized drift from spot to forward.
        
        This provides a market-implied risk-free rate that's more accurate than
        using a static treasury rate, as it captures the actual forward pricing
        in the options market including any dividend expectations.
        
        Args:
            underlying_price: Current spot price
            option_chain: Option chain with both calls and puts
            exp_date_str: Expiration date (YYYY-MM-DD)
            dte: Days to expiration
            
        Returns:
            Annualized drift rate (mu) for use in Black-Scholes
        """
        try:
            import numpy as np
            
            # Extract calls and puts from chain
            calls = option_chain.get('calls', [])
            puts = option_chain.get('puts', [])
            
            if not calls or not puts:
                logger.warning(f"No calls or puts for ATF calculation on {exp_date_str}, using mu=0")
                return 0.0
            
            # Build dict of strike -> (call_mid, put_mid)
            strike_data = {}
            
            # Process calls
            for call in calls:
                strike = call.get('strike')
                bid = call.get('bid')
                ask = call.get('ask')
                if strike is not None and bid is not None and ask is not None:
                    call_mid = (bid + ask) / 2
                    if strike not in strike_data:
                        strike_data[strike] = {'call': None, 'put': None}
                    strike_data[strike]['call'] = call_mid
            
            # Process puts
            for put in puts:
                strike = put.get('strike')
                bid = put.get('bid')
                ask = put.get('ask')
                if strike is not None and bid is not None and ask is not None:
                    put_mid = (bid + ask) / 2
                    if strike not in strike_data:
                        strike_data[strike] = {'call': None, 'put': None}
                    strike_data[strike]['put'] = put_mid
            
            # Filter to strikes with both call and put data
            valid_strikes = []
            for strike, data in strike_data.items():
                if data['call'] is not None and data['put'] is not None:
                    diff = abs(data['call'] - data['put'])
                    valid_strikes.append((strike, data['call'], data['put'], diff))
            
            if not valid_strikes:
                logger.warning(f"No valid strike pairs for ATF calculation on {exp_date_str}, using mu=0")
                return 0.0
            
            # Sort by strike
            valid_strikes.sort(key=lambda x: x[0])
            
            # Find strike with minimum |call - put| difference
            min_diff = float('inf')
            atf_strike = None
            
            for strike, call_mid, put_mid, diff in valid_strikes:
                if diff < min_diff:
                    min_diff = diff
                    atf_strike = strike
            
            if atf_strike is None:
                logger.warning(f"Could not determine ATF strike for {exp_date_str}, using mu=0")
                return 0.0
            
            # Try to interpolate for more precision if we have sign change
            strikes_with_diff = [(strike, call_mid - put_mid) 
                                 for strike, call_mid, put_mid, _ in valid_strikes]
            
            atf_interpolated = atf_strike
            for i in range(len(strikes_with_diff) - 1):
                strike1, diff1 = strikes_with_diff[i]
                strike2, diff2 = strikes_with_diff[i + 1]
                
                # Check if sign changes (crosses zero)
                if diff1 * diff2 < 0:
                    # Linear interpolation to find zero crossing
                    atf_interpolated = strike1 + (strike2 - strike1) * (-diff1) / (diff2 - diff1)
                    break
            
            # Calculate drift from spot to forward
            forward_price = atf_interpolated
            time_to_expiry = dte / 365.0
            
            if time_to_expiry <= 0:
                return 0.0
            
            # mu = ln(F/S) / T
            mu = np.log(forward_price / underlying_price) / time_to_expiry
            
            logger.info(f"ATF Analysis ({exp_date_str}): Spot=${underlying_price:.2f}, "
                       f"Forward=${forward_price:.2f}, Implied Drift={mu:.4f} ({mu*100:.2f}% annualized)")
            
            return mu
            
        except Exception as e:
            logger.error(f"Error calculating ATF drift for {exp_date_str}: {e}")
            return 0.0

