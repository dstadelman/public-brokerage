"""
Order confirmation card system for displaying detailed spread information.
Shows comprehensive analysis before order execution including Greeks, risk metrics, and market data.
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, date
from decimal import Decimal
import asyncio
import logging
import requests

from public_brokerage.client import PublicBrokerageClient
from public_brokerage.market_data import get_quotes, get_option_chain, get_option_greeks
from public_brokerage.models.market_data import Quote, OptionGreeks
from position_analyzer import CallSpread
import config

logger = logging.getLogger(__name__)


class ConfirmationCard:
    """Displays detailed order confirmation cards with market data and risk analysis."""
    
    def __init__(self, client: PublicBrokerageClient):
        self.client = client
        self.logger = logging.getLogger(__name__)
    
    def display_opening_spread_confirmation(
        self,
        symbol: str,
        short_expiration: str,
        short_strike: float,
        long_expiration: str,
        long_strike: float,
        quantity: int,
        max_wait_time: int = 42,
        account_id: Optional[str] = None,
        execute: bool = False
    ) -> bool:
        """
        Display confirmation card for opening a call spread.
        
        Returns:
            True if user confirms, False if cancelled
        """
        try:
            print("\n" + "=" * 80)
            print("📋 CALL SPREAD ORDER CONFIRMATION")
            print("=" * 80)
            
            # Get account ID if not provided
            if not account_id:
                from config import config
                account_id = config.get_default_account()
                
            if not account_id:
                print(f"❌ No account ID available for quote fetch")
                return False
            
            # Get underlying quote
            underlying_quote = self._get_underlying_quote(symbol, account_id)
            if not underlying_quote:
                print(f"❌ Could not fetch quote for {symbol}")
                return False
            
            print(f"📈 Underlying: {symbol} @ ${underlying_quote.last}")
            if underlying_quote.bid and underlying_quote.ask:
                print(f"📊 Bid/Ask: ${underlying_quote.bid} / ${underlying_quote.ask}")
            if underlying_quote.volume:
                print(f"📦 Volume: {underlying_quote.volume:,}")
            print("-" * 80)
            
            # Get option chain data for both legs using OSI formatter
            from utils import format_osi_symbol
            short_symbol = format_osi_symbol(symbol, short_expiration, 'CALL', short_strike)
            long_symbol = format_osi_symbol(symbol, long_expiration, 'CALL', long_strike)
            short_chain = self._get_option_data_by_symbol(short_symbol, account_id)
            long_chain = self._get_option_data_by_symbol(long_symbol, account_id)
            
            if not short_chain or not long_chain:
                print("❌ Could not fetch option chain data")
                return False
            
            # Display leg information
            print("🔴 SHORT LEG:")
            self._display_option_leg(short_chain, "SELL", quantity)
            
            print("\n🟢 LONG LEG:")
            self._display_option_leg(long_chain, "BUY", quantity)
            
            # Calculate spread pricing for opening call spreads
            # For opening: We buy the long option and sell the short option
            # spread_bid = best price we could get (what market will pay us)
            # spread_ask = worst price we'd pay (what market will charge us)
            spread_bid = long_chain['bid'] - short_chain['ask']  # Best execution price
            spread_ask = long_chain['ask'] - short_chain['bid']  # Worst execution price  
            spread_mid = (spread_bid + spread_ask) / 2
            
            print("\n💰 SPREAD PRICING:")
            print(f"   Bid: ${spread_bid:.2f}")
            print(f"   Ask: ${spread_ask:.2f}")
            print(f"   Mid: ${spread_mid:.2f}")
            print(f"   Width: ${abs(spread_ask - spread_bid):.2f}")
            
            # Calculate risk metrics
            spread_width = abs(long_strike - short_strike)
            if long_strike > short_strike:  # Debit spread
                max_profit = spread_width - spread_mid
                max_loss = spread_mid
                break_even = short_strike + spread_mid
                strategy_type = "DEBIT"
            else:  # Credit spread
                max_profit = spread_mid
                max_loss = spread_width - spread_mid
                break_even = short_strike - spread_mid
                strategy_type = "CREDIT"
            
            print(f"\n📊 RISK ANALYSIS ({strategy_type} SPREAD):")
            print(f"   Max Profit: ${max_profit * quantity:.2f}")
            print(f"   Max Loss: ${max_loss * quantity:.2f}")
            print(f"   Break Even: ${break_even:.2f}")
            if max_profit > 0:
                print(f"   Risk/Reward: {max_loss/max_profit:.2f}:1")
            else:
                print(f"   Risk/Reward: N/A (Max profit is $0)")
            
            # Display Greeks
            self._display_spread_greeks(short_chain, long_chain, quantity, account_id)
            
            # Display execution details
            print(f"\n⚙️  EXECUTION DETAILS:")
            if execute:
                print(f"   Mode: LIVE EXECUTION")
                print(f"   Strategy: Walk Limit Order")
                print(f"   Starting Price: ${spread_bid:.2f}")
                print(f"   Max Wait Time: {max_wait_time} seconds per increment")
            else:
                print(f"   Mode: DRY RUN (simulation only)")
                print(f"   Strategy: Walk Limit Order")
                print(f"   Starting Price: ${spread_bid:.2f}")
                print(f"   Max Wait Time: 1 second per increment (dry run)")
            print(f"   Commission: Will be calculated in preflight")
            
            # Days to expiration
            try:
                short_exp_date = datetime.strptime(short_expiration, '%Y-%m-%d').date()
                days_to_exp = (short_exp_date - datetime.now().date()).days
                print(f"   Days to Expiration: {days_to_exp}")
            except:
                pass
            
            print("=" * 80)
            
            # Get user confirmation
            while True:
                response = input("Confirm order? (y)es / (n)o / (d)etails: ").lower().strip()
                
                if response in ['y', 'yes']:
                    return True
                elif response in ['n', 'no']:
                    print("❌ Order cancelled by user")
                    return False
                elif response in ['d', 'details']:
                    self._show_detailed_analysis(symbol, short_chain, long_chain, quantity)
                else:
                    print("Please enter 'y', 'n', or 'd'")
        
        except Exception as e:
            logger.error(f"Error displaying confirmation card: {e}")
            print(f"❌ Error displaying confirmation: {e}")
            return False
    
    def display_closing_spread_confirmation(
        self,
        symbol: str,
        spreads: List[CallSpread],
        max_wait_time: int = 42,
        account_id: Optional[str] = None,
        execute: bool = False
    ) -> bool:
        """
        Display confirmation card for closing call spreads.
        
        Returns:
            True if user confirms, False if cancelled
        """
        try:
            print("\n" + "=" * 80)
            print("📋 CLOSE CALL SPREAD CONFIRMATION")
            print("=" * 80)
            
            # Get underlying quote
            if not account_id:
                from config import config
                account_id = config.get_default_account()
                
            if not account_id:
                print(f"❌ No account ID available for quote fetch")
                return False
                
            underlying_quote = self._get_underlying_quote(symbol, account_id)
            if not underlying_quote:
                print(f"❌ Could not fetch quote for {symbol}")
                return False
            
            total_quantity = 0
            total_current_value = 0.0
            overall_spread_bid = 0.0
            overall_spread_ask = 0.0
            
            # First, calculate overall spread pricing
            for spread in spreads:
                # Use the actual option symbols from the positions
                short_option_symbol = spread.short_leg.symbol
                long_option_symbol = spread.long_leg.symbol
                
                short_data = self._get_option_data_by_symbol(short_option_symbol, account_id)
                long_data = self._get_option_data_by_symbol(long_option_symbol, account_id)
                
                # Calculate spread pricing from individual leg quotes
                if short_data and long_data:
                    spread_bid = long_data['bid'] - short_data['ask'] 
                    spread_ask = long_data['ask'] - short_data['bid']
                    overall_spread_bid += spread_bid * spread.quantity
                    overall_spread_ask += spread_ask * spread.quantity
                    total_quantity += spread.quantity
            
            # Show overall spread pricing
            print(f"📈 {symbol} Calendar Spread")
            if total_quantity > 0:
                avg_spread_bid = overall_spread_bid / total_quantity
                avg_spread_ask = overall_spread_ask / total_quantity
                spread_width = avg_spread_ask - avg_spread_bid
                print(f"📊 Spread: ${avg_spread_bid:.2f} / ${avg_spread_ask:.2f} (Width: ${spread_width:.2f})")
            
            total_quantity = 0  # Reset for detailed calculation
            total_current_value = 0.0
            
            print(f"\n📍 POSITIONS TO CLOSE ({len(spreads)} spread(s)):")
            print("-" * 80)
            
            for i, spread in enumerate(spreads, 1):
                print(f"Spread {i}:")
                print(f"   Short: {spread.short_leg.strike_price} strike (Exp: {spread.short_leg.expiration_date})")
                print(f"   Long:  {spread.long_leg.strike_price} strike (Exp: {spread.long_leg.expiration_date})")
                print(f"   Quantity: {spread.quantity}")
                if spread.short_leg.expiration_date != spread.long_leg.expiration_date:
                    print(f"   Type: Calendar Spread")
                
                # Get current pricing for this spread using actual option symbols
                short_option_symbol = spread.short_leg.symbol
                long_option_symbol = spread.long_leg.symbol
                
                short_data = self._get_option_data_by_symbol(short_option_symbol, account_id)
                long_data = self._get_option_data_by_symbol(long_option_symbol, account_id)
                
                if short_data and long_data:
                    # For closing: we're buying back the short (paying ask) and selling the long (getting bid)
                    # Net result: long_bid - short_ask (what we'll receive for closing)
                    current_spread_bid = long_data['bid'] - short_data['ask'] 
                    current_spread_ask = long_data['ask'] - short_data['bid']
                    current_value = (current_spread_bid + current_spread_ask) / 2
                    
                    print(f"   📊 Spread Bid: ${current_spread_bid:.2f} | Ask: ${current_spread_ask:.2f}")
                    print(f"   📈 Short Leg: ${short_data['bid']:.2f}/${short_data['ask']:.2f} (Exp: {spread.short_leg.expiration_date})")
                    print(f"   📈 Long Leg:  ${long_data['bid']:.2f}/${long_data['ask']:.2f} (Exp: {spread.long_leg.expiration_date})")
                    print(f"   💰 Estimated Credit per Spread: ${current_value:.2f}")
                    total_current_value += current_value * spread.quantity
                else:
                    print(f"   ❌ Could not fetch option pricing data")
                
                total_quantity += spread.quantity
                print()
            
            print(f"💰 CLOSING ANALYSIS:")
            print(f"   Total Spreads: {total_quantity}")
            print(f"   Est. Closing Credit: ${total_current_value:.2f}")
            print(f"   Strategy: Walk Limit (Ask → Bid)")
            if execute:
                print(f"   Mode: LIVE EXECUTION")
                print(f"   Max Wait Time: {max_wait_time} seconds per increment")
            else:
                print(f"   Mode: DRY RUN (simulation only)")
                print(f"   Max Wait Time: 1 second per increment (dry run)")
            
            print("=" * 80)
            
            # Get user confirmation
            while True:
                response = input("Confirm closing order? (y)es / (n)o / (d)etails: ").lower().strip()
                
                if response in ['y', 'yes']:
                    return True
                elif response in ['n', 'no']:
                    print("❌ Order cancelled by user")
                    return False
                elif response in ['d', 'details']:
                    print("📊 Detailed analysis not yet implemented for closing spreads")
                else:
                    print("Please enter 'y', 'n', or 'd'")
        
        except Exception as e:
            logger.error(f"Error displaying closing confirmation card: {e}")
            print(f"❌ Error displaying confirmation: {e}")
            return False
    
    def _get_underlying_quote(self, symbol: str, account_id: str) -> Optional[Quote]:
        """Get real-time quote for underlying symbol."""
        try:
            from public_brokerage.models.common import Instrument, InstrumentType
            
            # Create instrument object
            instrument = Instrument(symbol=symbol, type=InstrumentType.EQUITY)
            quotes = get_quotes(self.client, account_id, [instrument])
            return quotes[0] if quotes else None
        except Exception as e:
            logger.error(f"Error fetching quote for {symbol}: {e}")
            return None
    
    def _get_option_data_by_symbol(
        self, 
        option_symbol: str,
        account_id: str
    ) -> Optional[Dict]:
        """Get option quote data for specific option symbol."""
        try:
            from public_brokerage.models.common import Instrument, InstrumentType
            
            # Strip -OPTION suffix if present
            clean_symbol = option_symbol.replace('-OPTION', '')
            logger.info(f"Getting quote for option symbol: {clean_symbol}")
            
            # Create instrument object for the option
            instrument = Instrument(symbol=clean_symbol, type=InstrumentType.OPTION)
            
            # Get quote for this specific option
            quotes = get_quotes(self.client, account_id, [instrument])
            
            if quotes and len(quotes) > 0:
                quote = quotes[0]
                return {
                    'symbol': option_symbol,
                    'bid': float(quote.bid) if quote.bid else 0.0,
                    'ask': float(quote.ask) if quote.ask else 0.0,
                    'last': float(quote.last) if quote.last else 0.0,
                    'volume': quote.volume or 0,
                    'openInterest': quote.openInterest or 0,
                    'impliedVolatility': 0.0  # May not be available in quotes
                }
            else:
                logger.warning(f"No quote data returned for option {option_symbol}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching option quote for {option_symbol}: {e}")
            return None
    
    def _display_option_leg(self, option_data: Dict, action: str, quantity: int) -> None:
        """Display information for one leg of the spread."""
        print(f"   {action} {quantity} × {option_data['symbol']}")
        print(f"   Bid/Ask: ${option_data['bid']:.2f} / ${option_data['ask']:.2f}")
        print(f"   Last: ${option_data['last']:.2f}")
        print(f"   Volume: {option_data['volume']:,}")
        print(f"   Open Interest: {option_data['openInterest']:,}")
        print(f"   IV: {option_data['impliedVolatility']:.1%}")
    

    
    def _display_spread_greeks(self, short_option: Dict, long_option: Dict, quantity: int, account_id: str) -> None:
        """Display net Greeks for the spread."""
        try:
            # Get Greeks data
            short_greeks = self._get_option_greeks(short_option['symbol'], account_id)
            long_greeks = self._get_option_greeks(long_option['symbol'], account_id)
            
            if short_greeks and long_greeks:
                # Convert to float and calculate net Greeks (short position is negative)
                short_delta = float(short_greeks.delta) if short_greeks.delta else 0.0
                short_gamma = float(short_greeks.gamma) if short_greeks.gamma else 0.0
                short_theta = float(short_greeks.theta) if short_greeks.theta else 0.0
                short_vega = float(short_greeks.vega) if short_greeks.vega else 0.0
                
                long_delta = float(long_greeks.delta) if long_greeks.delta else 0.0
                long_gamma = float(long_greeks.gamma) if long_greeks.gamma else 0.0
                long_theta = float(long_greeks.theta) if long_greeks.theta else 0.0
                long_vega = float(long_greeks.vega) if long_greeks.vega else 0.0
                
                net_delta = (-short_delta + long_delta) * quantity
                net_gamma = (-short_gamma + long_gamma) * quantity
                net_theta = (-short_theta + long_theta) * quantity
                net_vega = (-short_vega + long_vega) * quantity
                
                print(f"\n🔢 NET GREEKS (for {quantity} spreads):")
                print(f"   Delta: {net_delta:.3f}")
                print(f"   Gamma: {net_gamma:.3f}")
                print(f"   Theta: {net_theta:.3f}")
                print(f"   Vega:  {net_vega:.3f}")
        except Exception as e:
            logger.warning(f"Could not fetch Greeks: {e}")
    
    def _get_option_greeks(self, option_symbol: str, account_id: str) -> Optional[OptionGreeks]:
        """Get Greeks for a specific option."""
        try:
            greeks_response = get_option_greeks(self.client, account_id, option_symbol)
            return greeks_response
        except Exception as e:
            logger.error(f"Error fetching Greeks for {option_symbol}: {e}")
            return None
            
            for greek in greeks_response.greeks:
                if greek.symbol == option_symbol:
                    return greek
            return None
        except Exception as e:
            logger.error(f"Error fetching Greeks for {option_symbol}: {e}")
            return None
    
    def _show_detailed_analysis(
        self, 
        symbol: str, 
        short_option: Dict, 
        long_option: Dict, 
        quantity: int
    ) -> None:
        """Show extended analysis details."""
        print("\n" + "=" * 60)
        print("📊 DETAILED ANALYSIS")
        print("=" * 60)
        
        print("🔍 Liquidity Analysis:")
        short_liquidity = "Good" if short_option['volume'] > 100 else "Limited"
        long_liquidity = "Good" if long_option['volume'] > 100 else "Limited"
        
        print(f"   Short Leg Liquidity: {short_liquidity}")
        print(f"   Long Leg Liquidity: {long_liquidity}")
        
        # IV analysis
        iv_diff = abs(short_option['impliedVolatility'] - long_option['impliedVolatility'])
        print(f"\n📈 Volatility Analysis:")
        print(f"   IV Skew: {iv_diff:.1%}")
        if iv_diff > 0.05:
            print("   ⚠️  Significant IV skew detected")
        
        print(f"\n💡 Strategy Notes:")
        print(f"   • This is a limited risk/reward strategy")
        print(f"   • Maximum time to profit: expiration")
        print(f"   • Theta decay affects both legs")
        print(f"   • Consider early closure if 50% max profit reached")
        
        input("\nPress Enter to continue...")
    
    def display_single_leg_confirmation(
        self,
        symbol: str,
        expiration: str,
        option_type: str,
        strike: float,
        quantity: int,
        strategy: str = "open",  # "open" or "close"
        max_wait_time: int = 42,
        account_id: Optional[str] = None,
        execute: bool = False
    ) -> bool:
        """
        Display confirmation card for single-leg option orders.
        
        Args:
            symbol: Underlying symbol
            expiration: Option expiration date (YYYY-MM-DD)
            option_type: "C" for call, "P" for put
            strike: Strike price
            quantity: Number of contracts (positive=buy, negative=sell)
            strategy: "open" for new position, "close" for closing existing
            max_wait_time: Seconds to wait per price level
            account_id: Account ID
            execute: True for live execution, False for dry run
            
        Returns:
            True if user confirms, False if cancelled
        """
        try:
            # Determine action and position type
            is_call = option_type.upper() in ['C', 'CALL']
            option_type_display = "CALL" if is_call else "PUT"
            
            if strategy == "open":
                action = "BUY" if quantity > 0 else "SELL"
                action_verb = "Opening" if quantity > 0 else "Selling"
                position_type = "LONG" if quantity > 0 else "SHORT"
            else:  # close
                action = "SELL" if quantity < 0 else "BUY"
                action_verb = "Closing" if quantity < 0 else "Covering"
                position_type = "LONG" if quantity < 0 else "SHORT"
            
            print("\n" + "=" * 80)
            print(f"📋 {option_type_display} OPTION ORDER CONFIRMATION")
            print("=" * 80)
            
            # Get account ID if not provided
            if not account_id:
                from config import config
                account_id = config.get_default_account()
                
            if not account_id:
                print(f"❌ No account ID available for quote fetch")
                return False
            
            # Get underlying quote
            underlying_quote = self._get_underlying_quote(symbol, account_id)
            if not underlying_quote:
                print(f"❌ Could not fetch quote for {symbol}")
                return False
            
            print(f"📈 Underlying: {symbol} @ ${underlying_quote.last}")
            if underlying_quote.bid and underlying_quote.ask:
                print(f"📊 Bid/Ask: ${underlying_quote.bid} / ${underlying_quote.ask}")
            if underlying_quote.volume:
                print(f"📦 Volume: {underlying_quote.volume:,}")
            print("-" * 80)
            
            # Get option data using OSI formatter
            from utils import format_osi_symbol
            option_symbol = format_osi_symbol(symbol, expiration, option_type, strike)
            option_data = self._get_option_data_by_symbol(option_symbol, account_id)
            
            if not option_data:
                print("❌ Could not fetch option data")
                return False
            
            # Display option information
            print(f"🎯 OPTION DETAILS:")
            print(f"   Symbol: {option_symbol}")
            print(f"   Type: {option_type_display}")
            print(f"   Strike: ${strike}")
            print(f"   Expiration: {expiration}")
            print(f"   Action: {action} {abs(quantity)} contracts")
            print(f"   Strategy: {action_verb} {position_type} position")
            
            # Display current pricing
            print(f"\n💰 CURRENT PRICING:")
            print(f"   Bid: ${option_data['bid']:.2f}")
            print(f"   Ask: ${option_data['ask']:.2f}")
            print(f"   Last: ${option_data['last']:.2f}")
            print(f"   Mid: ${(option_data['bid'] + option_data['ask']) / 2:.2f}")
            print(f"   Spread: ${option_data['ask'] - option_data['bid']:.2f}")
            
            # Calculate cost/proceeds
            if quantity > 0:  # Buying
                target_price = option_data['ask']
                estimated_cost = target_price * abs(quantity) * 100  # Options are per 100 shares
                print(f"\n💸 ESTIMATED COST:")
                print(f"   Maximum Cost: ${estimated_cost:.2f}")
                print(f"   Walk Limit will try to get better price starting at bid")
            else:  # Selling
                target_price = option_data['bid']
                estimated_proceeds = target_price * abs(quantity) * 100
                print(f"\n💰 ESTIMATED PROCEEDS:")
                print(f"   Minimum Proceeds: ${estimated_proceeds:.2f}")
                print(f"   Walk Limit will try to get better price starting at ask")
            
            # Display option Greeks
            self._display_single_option_greeks(option_data, quantity, account_id)
            
            # Calculate moneyness and risk metrics
            self._display_single_leg_risk_analysis(
                float(underlying_quote.last), strike, is_call, quantity, 
                option_data, strategy
            )
            
            # Display execution details
            print(f"\n⚙️  EXECUTION DETAILS:")
            if execute:
                print(f"   Mode: LIVE EXECUTION")
                print(f"   Strategy: Walk Limit Order")
                if quantity > 0:
                    print(f"   Starting Price: ${option_data['bid']:.2f} (walking toward ${option_data['ask']:.2f})")
                else:
                    print(f"   Starting Price: ${option_data['ask']:.2f} (walking toward ${option_data['bid']:.2f})")
                print(f"   Max Wait Time: {max_wait_time} seconds per increment")
            else:
                print(f"   Mode: DRY RUN (simulation only)")
                print(f"   Strategy: Walk Limit Order")
                print(f"   Max Wait Time: 1 second per increment (dry run)")
            print(f"   Commission: Will be calculated in preflight")
            
            # Days to expiration
            try:
                exp_date = datetime.strptime(expiration, '%Y-%m-%d').date()
                days_to_exp = (exp_date - datetime.now().date()).days
                print(f"   Days to Expiration: {days_to_exp}")
            except:
                pass
            
            print("=" * 80)
            
            # Get user confirmation
            while True:
                response = input("Confirm order? (y)es / (n)o / (d)etails: ").lower().strip()
                
                if response in ['y', 'yes']:
                    return True
                elif response in ['n', 'no']:
                    print("❌ Order cancelled by user")
                    return False
                elif response in ['d', 'details']:
                    self._show_single_leg_detailed_analysis(symbol, option_data, quantity, underlying_quote.last)
                else:
                    print("Please enter 'y', 'n', or 'd'")
        
        except Exception as e:
            logger.error(f"Error displaying single leg confirmation card: {e}")
            print(f"❌ Error displaying confirmation: {e}")
            return False
    
    def _display_single_option_greeks(self, option_data: Dict, quantity: int, account_id: str) -> None:
        """Display Greeks for a single option position."""
        try:
            # Get Greeks data
            greeks = self._get_option_greeks(option_data['symbol'], account_id)
            
            if greeks:
                # Convert to float
                delta = float(greeks.delta) if greeks.delta else 0.0
                gamma = float(greeks.gamma) if greeks.gamma else 0.0
                theta = float(greeks.theta) if greeks.theta else 0.0
                vega = float(greeks.vega) if greeks.vega else 0.0
                
                # Apply quantity and position direction
                position_delta = delta * quantity
                position_gamma = gamma * quantity
                position_theta = theta * quantity
                position_vega = vega * quantity
                
                print(f"\n🔢 OPTION GREEKS (for {quantity} contracts):")
                print(f"   Delta: {position_delta:.3f}")
                print(f"   Gamma: {position_gamma:.3f}")
                print(f"   Theta: {position_theta:.3f}")
                print(f"   Vega:  {position_vega:.3f}")
                print(f"   IV:    {option_data['impliedVolatility']:.1%}")
        except Exception as e:
            logger.warning(f"Could not fetch Greeks: {e}")
    
    def _display_single_leg_risk_analysis(
        self, 
        underlying_price: float, 
        strike: float, 
        is_call: bool, 
        quantity: int,
        option_data: Dict,
        strategy: str
    ) -> None:
        """Display risk analysis for single-leg option position."""
        print(f"\n📊 RISK ANALYSIS:")
        
        # Calculate moneyness
        if is_call:
            moneyness = underlying_price - strike
            itm_status = "ITM" if moneyness > 0 else "OTM" if moneyness < 0 else "ATM"
        else:  # put
            moneyness = strike - underlying_price
            itm_status = "ITM" if moneyness > 0 else "OTM" if moneyness < 0 else "ATM"
        
        print(f"   Moneyness: {itm_status} by ${abs(moneyness):.2f}")
        
        # Calculate intrinsic and time value
        intrinsic_value = max(0, moneyness) if moneyness > 0 else 0
        time_value = float(option_data['last']) - intrinsic_value
        
        print(f"   Intrinsic Value: ${intrinsic_value:.2f}")
        print(f"   Time Value: ${time_value:.2f}")
        
        # Risk metrics based on position type
        option_price = float(option_data['last'])
        contract_value = option_price * 100  # Options control 100 shares
        
        if quantity > 0:  # Long position
            max_loss = option_price * abs(quantity) * 100
            max_profit = "Unlimited" if is_call else f"${(strike * abs(quantity) * 100) - max_loss:.2f}"
            print(f"   Max Loss: ${max_loss:.2f} (premium paid)")
            print(f"   Max Profit: {max_profit}")
            
            # Breakeven
            if is_call:
                breakeven = strike + option_price
                print(f"   Breakeven: ${breakeven:.2f} (strike + premium)")
            else:
                breakeven = strike - option_price
                print(f"   Breakeven: ${breakeven:.2f} (strike - premium)")
                
        else:  # Short position
            max_profit = option_price * abs(quantity) * 100
            max_loss = "Unlimited" if is_call else f"${(strike * abs(quantity) * 100) - max_profit:.2f}"
            print(f"   Max Profit: ${max_profit:.2f} (premium received)")
            print(f"   Max Loss: {max_loss}")
            
            # Breakeven
            if is_call:
                breakeven = strike + option_price
                print(f"   Breakeven: ${breakeven:.2f} (strike + premium)")
            else:
                breakeven = strike - option_price
                print(f"   Breakeven: ${breakeven:.2f} (strike - premium)")
        
        # Liquidity analysis
        print(f"\n🔍 LIQUIDITY ANALYSIS:")
        volume = option_data.get('volume', 0)
        open_interest = option_data.get('openInterest', 0)
        
        liquidity_score = "Good" if volume > 100 and open_interest > 500 else "Limited"
        print(f"   Volume: {volume:,}")
        print(f"   Open Interest: {open_interest:,}")
        print(f"   Liquidity: {liquidity_score}")
        
        if liquidity_score == "Limited":
            print("   ⚠️  Limited liquidity - wider spreads expected")
    
    def _show_single_leg_detailed_analysis(
        self, 
        symbol: str, 
        option_data: Dict, 
        quantity: int, 
        underlying_price: float
    ) -> None:
        """Show detailed analysis for single-leg option."""
        print("\n" + "=" * 60)
        print("📊 DETAILED SINGLE LEG ANALYSIS")
        print("=" * 60)
        
        print(f"📈 Market Data:")
        print(f"   Underlying: {symbol} @ ${underlying_price}")
        print(f"   Option: {option_data['symbol']}")
        print(f"   Last Trade: ${option_data['last']:.2f}")
        print(f"   Bid/Ask: ${option_data['bid']:.2f} / ${option_data['ask']:.2f}")
        print(f"   Volume: {option_data.get('volume', 0):,}")
        print(f"   Open Interest: {option_data.get('openInterest', 0):,}")
        print(f"   Implied Volatility: {option_data['impliedVolatility']:.1%}")
        
        print(f"\n💡 Strategy Notes:")
        if quantity > 0:
            print(f"   • Long option position - limited risk, unlimited upside potential")
            print(f"   • Theta decay works against you")
            print(f"   • Benefits from increased volatility")
            print(f"   • Consider profit-taking at 50-100% gain")
        else:
            print(f"   • Short option position - limited profit, significant risk")
            print(f"   • Theta decay works in your favor")
            print(f"   • Harmed by increased volatility")
            print(f"   • Consider closing at 25-50% max profit")
        
        input("\nPress Enter to continue...")
    
    def display_ff_confirmation(
        self,
        symbol: str,
        short_expiration: str,
        long_expiration: str,
        strike: float,
        quantity: int,
        ff_threshold: float,
        is_opening: bool,
        max_wait_time: int = 42,
        account_id: Optional[str] = None,
        execute: bool = False,
        analyzer=None  # ForwardFactorAnalyzer instance
    ) -> bool:
        """
        Display confirmation card for forward factor based calendar spread trades.
        
        Args:
            symbol: Underlying symbol
            short_expiration: Short leg expiration (YYYY-MM-DD)
            long_expiration: Long leg expiration (YYYY-MM-DD)
            strike: Strike price for both legs
            quantity: Number of spreads
            ff_threshold: FF threshold (min_ff for opening, max_ff for closing)
            is_opening: True for opening, False for closing
            max_wait_time: Max wait time per price level
            account_id: Account ID
            execute: Whether to execute actual orders
            analyzer: ForwardFactorAnalyzer instance (required)
            
        Returns:
            True if user confirms, False if cancelled
        """
        try:
            action = "OPENING" if is_opening else "CLOSING"
            print("\n" + "=" * 80)
            print(f"📋 FORWARD FACTOR CALENDAR SPREAD - {action}")
            print("=" * 80)
            
            # Get account ID if not provided
            if not account_id:
                from config import config
                account_id = config.get_default_account()
                
            if not account_id:
                print(f"❌ No account ID available")
                return False
            
            if analyzer is None:
                print(f"❌ ForwardFactorAnalyzer required")
                return False
            
            # Get underlying quote
            underlying_quote = self._get_underlying_quote(symbol, account_id)
            if not underlying_quote:
                print(f"❌ Could not fetch quote for {symbol}")
                return False
            
            print(f"📈 Underlying: {symbol} @ ${underlying_quote.last}")
            if underlying_quote.bid and underlying_quote.ask:
                print(f"📊 Bid/Ask: ${underlying_quote.bid} / ${underlying_quote.ask}")
            print("-" * 80)
            
            # Get option chain data
            from datetime import datetime
            from public_brokerage.models.common import Instrument, InstrumentType
            
            instrument = Instrument(symbol=symbol, type=InstrumentType.EQUITY)
            short_date = datetime.strptime(short_expiration, "%Y-%m-%d").date()
            long_date = datetime.strptime(long_expiration, "%Y-%m-%d").date()
            
            short_chain = get_option_chain(self.client, account_id, instrument, short_date)
            long_chain = get_option_chain(self.client, account_id, instrument, long_date)
            
            # Find specific options
            short_option = analyzer._find_option_in_chain(short_chain, strike)
            long_option = analyzer._find_option_in_chain(long_chain, strike)
            
            if not short_option or not long_option:
                print(f"❌ Could not find strike {strike} in option chains")
                return False
            
            # Calculate spread pricing
            spread_bid = long_option['bid'] - short_option['ask']
            spread_ask = long_option['ask'] - short_option['bid']
            spread_mid = (spread_bid + spread_ask) / 2
            spread_width = spread_ask - spread_bid
            
            # Calculate DTEs
            from datetime import datetime
            today = datetime.now().date()
            short_date = datetime.strptime(short_expiration, "%Y-%m-%d").date()
            long_date = datetime.strptime(long_expiration, "%Y-%m-%d").date()
            short_dte = (short_date - today).days
            long_dte = (long_date - today).days
            
            print("🔴 SHORT LEG:")
            print(f"   Expiration: {short_expiration} ({short_dte} DTE)")
            print(f"   Strike: ${strike}")
            print(f"   Bid/Ask: ${short_option['bid']:.2f} / ${short_option['ask']:.2f}")
            
            print("\n🟢 LONG LEG:")
            print(f"   Expiration: {long_expiration} ({long_dte} DTE)")
            print(f"   Strike: ${strike}")
            print(f"   Bid/Ask: ${long_option['bid']:.2f} / ${long_option['ask']:.2f}")
            
            print("\n💰 SPREAD PRICING:")
            print(f"   Bid:   ${spread_bid:.2f}")
            print(f"   Mid:   ${spread_mid:.2f}")
            print(f"   Ask:   ${spread_ask:.2f}")
            print(f"   Width: ${spread_width:.2f}")
            
            # Calculate FF grid using new grid-based approach
            try:
                # Calculate FF grid (20 steps through bid-ask spread)
                ff_grid = analyzer.calculate_ff_grid(
                    short_bid=float(short_option['bid']),
                    short_ask=float(short_option['ask']),
                    long_bid=float(long_option['bid']),
                    long_ask=float(long_option['ask']),
                    underlying_price=float(underlying_quote.last),
                    strike=float(strike),
                    short_dte=short_dte,
                    long_dte=long_dte
                )
                
                # Get FF at key execution points
                ff_at_bid = ff_grid[0]['ff'] if ff_grid and ff_grid[0]['ff'] is not None else None
                ff_at_mid = None
                ff_at_ask = ff_grid[-1]['ff'] if ff_grid and ff_grid[-1]['ff'] is not None else None
                
                # Find mid point in grid (closest to 50%)
                for step in ff_grid:
                    if abs(step['pct'] - 0.5) < 0.05:  # Within 5% of midpoint
                        if step['ff'] is not None:
                            ff_at_mid = step['ff']
                            break
                
                # Find target price using grid
                direction = 'open' if is_opening else 'close'
                result = analyzer.find_target_price_for_ff(ff_grid, target_ff=ff_threshold, direction=direction)
                
                print("\n📊 FORWARD FACTOR ANALYSIS (Grid-Based):")
                print(f"   Target FF Threshold: {ff_threshold:.3f}")
                
                # Display FF at key points
                print(f"\n   FF Range Across Bid-Ask Spread:")
                if ff_at_bid is not None:
                    ff_str = f"{ff_at_bid:.3f}" if not float('inf') == ff_at_bid else "∞ (extreme backwardation)"
                    print(f"   • At BID (${spread_bid:.2f}): FF = {ff_str}")
                if ff_at_mid is not None:
                    print(f"   • At MID (${spread_mid:.2f}): FF = {ff_at_mid:.3f}")
                if ff_at_ask is not None:
                    print(f"   • At ASK (${spread_ask:.2f}): FF = {ff_at_ask:.3f}")
                
                # Calculate ATF rates for display
                short_atf_rate = analyzer.calculate_atf_drift(float(underlying_quote.last), short_chain, short_expiration, short_dte)
                long_atf_rate = analyzer.calculate_atf_drift(float(underlying_quote.last), long_chain, long_expiration, long_dte)
                print(f"\n   Market-Implied Drift Rates:")
                print(f"   • Short Leg ATF: {short_atf_rate*100:.2f}%")
                print(f"   • Long Leg ATF: {long_atf_rate*100:.2f}%")
                
                # Show target and feasibility
                if result:
                    target_price, target_pct, target_ff = result
                    print(f"\n   🎯 Target Found:")
                    print(f"   • Target Price: ${target_price:.2f} ({target_pct:.1%} through spread)")
                    print(f"   • FF at Target: {target_ff:.3f}")
                    
                    # Walk strategy
                    if is_opening:
                        # Opening: Walk BID UP to target_price
                        feasible = True  # Already checked by find_target_price_for_ff
                        walk_direction = f"BID (${spread_bid:.2f}) → Target (${target_price:.2f})"
                        capture_range = f"${spread_bid:.2f} to ${target_price:.2f}"
                        print(f"\n   🚶 Walk Strategy:")
                        print(f"   • Direction: {walk_direction}")
                        print(f"   • Capture ALL prices in range: {capture_range}")
                        print(f"   • ALL steps have FF >= {ff_threshold:.3f} ✓")
                        print(f"   • ✅ FEASIBLE: Walk captures {int(target_pct * 20)} of 20 grid steps")
                    else:
                        # Closing: Walk ASK DOWN to target_price
                        feasible = True
                        walk_direction = f"ASK (${spread_ask:.2f}) → Target (${target_price:.2f})"
                        capture_range = f"${target_price:.2f} to ${spread_ask:.2f}"
                        print(f"\n   🚶 Walk Strategy:")
                        print(f"   • Direction: {walk_direction}")
                        print(f"   • Capture ALL prices in range: {capture_range}")
                        print(f"   • ALL steps have FF <= {ff_threshold:.3f} ✓")
                        print(f"   • ✅ FEASIBLE: Walk captures {int(target_pct * 20)} of 20 grid steps")
                else:
                    # Not feasible
                    feasible = False
                    print(f"\n   ❌ NOT FEASIBLE:")
                    if is_opening:
                        print(f"   • No price in bid-ask range achieves FF >= {ff_threshold:.3f}")
                        if ff_at_bid is not None:
                            print(f"   • Best available FF: {ff_at_bid:.3f} at BID")
                            if ff_at_bid < ff_threshold:
                                suggested = ff_at_bid * 0.9  # Suggest 10% lower threshold
                                print(f"   • Try lower threshold: --min_ff={suggested:.3f}")
                    else:
                        print(f"   • No price in bid-ask range achieves FF <= {ff_threshold:.3f}")
                        if ff_at_ask is not None:
                            print(f"   • Best available FF: {ff_at_ask:.3f} at ASK")
                            if ff_at_ask > ff_threshold:
                                suggested = ff_at_ask * 1.1  # Suggest 10% higher threshold
                                print(f"   • Try higher threshold: --max_ff={suggested:.3f}")
                    
                    print("\n⚠️  WARNING: Trade is not feasible at current market prices")
                    
            except Exception as e:
                print(f"\n❌ Error calculating FF grid analysis: {e}")
                import traceback
                traceback.print_exc()
                return False
            
            # Trade summary
            print("\n💼 TRADE SUMMARY:")
            print(f"   Strategy: Forward Factor Calendar Spread")
            print(f"   Action: {action}")
            print(f"   Quantity: {quantity} spread(s)")
            print(f"   Total Cost: ~${spread_mid * quantity * 100:.2f}" if is_opening else f"   Est. Credit: ~${spread_mid * quantity * 100:.2f}")
            if execute:
                print(f"   Mode: LIVE EXECUTION")
                print(f"   Max Wait Time: {max_wait_time}s per price level")
            else:
                print(f"   Mode: DRY RUN (simulation)")
                print(f"   Max Wait Time: 1s per level (dry run)")
            
            print("=" * 80)
            
            # Get user confirmation
            while True:
                response = input("Confirm trade? (y)es / (n)o / (d)etails: ").lower().strip()
                
                if response in ['y', 'yes']:
                    return True
                elif response in ['n', 'no']:
                    print("❌ Trade cancelled by user")
                    return False
                elif response in ['d', 'details']:
                    # Use ff_at_mid as "current_ff" for detailed analysis
                    display_ff = ff_at_mid if ff_at_mid is not None else (ff_at_bid if ff_at_bid is not None else ff_at_ask)
                    self._show_ff_detailed_analysis(
                        symbol, short_option, long_option, 
                        display_ff, ff_threshold, 
                        underlying_quote.last, is_opening
                    )
                else:
                    print("Please enter 'y', 'n', or 'd'")
                    
        except Exception as e:
            logger.error(f"Error displaying FF confirmation: {e}", exc_info=True)
            print(f"❌ Error displaying confirmation: {e}")
            return False
    
    def _show_ff_detailed_analysis(
        self,
        symbol: str,
        short_option: Dict,
        long_option: Dict,
        current_ff: Optional[float],
        target_ff: float,
        underlying_price: float,
        is_opening: bool
    ) -> None:
        """Show detailed forward factor analysis."""
        print("\n" + "=" * 80)
        print("📊 DETAILED FORWARD FACTOR ANALYSIS")
        print("=" * 80)
        
        print(f"\n📈 Forward Volatility Concept:")
        print(f"   Forward volatility represents the market's expectation of")
        print(f"   volatility between the front and back expiration dates.")
        print(f"   ")
        print(f"   Forward Factor (FF) = (Front IV - Forward Vol) / Forward Vol")
        print(f"   ")
        print(f"   FF > 0: Contango (front option more expensive than implied)")
        print(f"   FF < 0: Backwardation (front option cheaper than implied)")
        print(f"   FF = 0: Fair value (no mispricing)")
        
        print(f"\n🎯 Current Trade Analysis:")
        print(f"   Underlying: {symbol} @ ${underlying_price:.2f}")
        print(f"   Short Leg IV: {short_option['impliedVolatility']:.1%}")
        print(f"   Long Leg IV: {long_option['impliedVolatility']:.1%}")
        if current_ff is not None:
            print(f"   Current FF: {current_ff:.3f}")
            if current_ff > 0.5:
                print(f"   → Strong contango (front leg expensive)")
            elif current_ff > 0.2:
                print(f"   → Moderate contango")
            elif current_ff > -0.2:
                print(f"   → Near fair value")
            else:
                print(f"   → Backwardation (front leg cheap)")
        
        print(f"\n🎲 Strategy Rationale:")
        if is_opening:
            print(f"   OPENING at FF >= {target_ff:.3f}:")
            print(f"   • Buying calendar when front leg is relatively expensive")
            print(f"   • Expecting mean reversion (FF to decrease)")
            print(f"   • Profit if: Front decays faster or back gains value")
        else:
            print(f"   CLOSING at FF <= {target_ff:.3f}:")
            print(f"   • Selling calendar when target FF reached")
            print(f"   • Taking profit or cutting loss")
            print(f"   • Goal: Exit at favorable FF level")
        
        print(f"\n⚠️  Risk Considerations:")
        print(f"   • Calendar spreads are vega-positive (benefit from IV increase)")
        print(f"   • Time decay: Front leg decays faster than back leg")
        print(f"   • Pin risk: If underlying near strike at front expiration")
        print(f"   • Gamma risk: Large moves can hurt calendars")
        print(f"   • Early assignment risk if front leg is ITM")
        
        print("=" * 80)
        input("\nPress Enter to continue...")

