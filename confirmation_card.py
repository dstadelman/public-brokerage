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
        account_id: Optional[str] = None
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
            
            # Calculate spread pricing
            spread_bid, spread_ask = self._calculate_spread_pricing(short_chain, long_chain)
            spread_mid = (spread_bid + spread_ask) / 2
            
            print("\n💰 SPREAD PRICING:")
            print(f"   Bid: ${spread_bid:.2f}")
            print(f"   Ask: ${spread_ask:.2f}")
            print(f"   Mid: ${spread_mid:.2f}")
            print(f"   Width: ${spread_ask - spread_bid:.2f}")
            
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
            print(f"   Strategy: Walk Limit Order")
            print(f"   Starting Price: ${spread_bid:.2f}")
            print(f"   Max Wait Time: {max_wait_time} seconds per increment")
            print(f"   Est. Commission: $2.10 (2 legs × $0.65 + $0.80 base)")
            
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
        account_id: Optional[str] = None
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
            print(f"   Max Wait Time: {max_wait_time} seconds per increment")
            
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
    
    def _calculate_spread_pricing(self, short_option: Dict, long_option: Dict) -> Tuple[float, float]:
        """Calculate bid/ask pricing for the spread."""
        # For opening a call spread (sell short, buy long):
        # Spread bid = short_bid - long_ask (worst case for us)
        # Spread ask = short_ask - long_bid (best case for us)
        spread_bid = short_option['bid'] - long_option['ask']
        spread_ask = short_option['ask'] - long_option['bid']
        
        return max(spread_bid, 0.0), max(spread_ask, 0.0)
    
    def _display_spread_greeks(self, short_option: Dict, long_option: Dict, quantity: int, account_id: str) -> None:
        """Display net Greeks for the spread."""
        try:
            # Get Greeks data
            short_greeks = self._get_option_greeks(short_option['symbol'], account_id)
            long_greeks = self._get_option_greeks(long_option['symbol'], account_id)
            
            if short_greeks and long_greeks:
                # Calculate net Greeks (short position is negative)
                net_delta = (-short_greeks.delta + long_greeks.delta) * quantity
                net_gamma = (-short_greeks.gamma + long_greeks.gamma) * quantity
                net_theta = (-short_greeks.theta + long_greeks.theta) * quantity
                net_vega = (-short_greeks.vega + long_greeks.vega) * quantity
                
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
