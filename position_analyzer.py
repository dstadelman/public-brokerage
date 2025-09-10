"""
Position analyzer for identifying and managing option spreads.
Analyzes current positions to detect call spreads, put spreads, and other multi-leg strategies.
"""

from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
from datetime import datetime, date
from collections import defaultdict
import logging

from public_brokerage.models.portfolio import Position
from public_brokerage.models.common import OptionType, InstrumentType

logger = logging.getLogger(__name__)


@dataclass
class SpreadLeg:
    """Represents one leg of an option spread."""
    position: Position
    symbol: str
    underlying: str
    option_type: OptionType
    strike_price: float
    expiration_date: date
    quantity: float
    is_long: bool  # True for long positions, False for short


@dataclass
class CallSpread:
    """Represents a call spread position."""
    underlying: str
    short_leg: SpreadLeg
    long_leg: SpreadLeg
    quantity: int  # Number of spreads
    spread_width: float
    net_quantity: float  # Net position quantity
    is_debit_spread: bool  # True for debit spread, False for credit spread
    
    @property
    def max_profit(self) -> float:
        """Calculate maximum profit for the spread."""
        if self.is_debit_spread:
            return self.spread_width - abs(self.net_quantity)
        else:
            return abs(self.net_quantity)
    
    @property
    def max_loss(self) -> float:
        """Calculate maximum loss for the spread."""
        if self.is_debit_spread:
            return abs(self.net_quantity)
        else:
            return self.spread_width - abs(self.net_quantity)
    
    @property
    def break_even(self) -> float:
        """Calculate break-even point."""
        if self.is_debit_spread:
            return self.long_leg.strike_price + abs(self.net_quantity)
        else:
            return self.short_leg.strike_price + abs(self.net_quantity)


@dataclass
class PutSpread:
    """Represents a put spread position."""
    underlying: str
    short_leg: SpreadLeg
    long_leg: SpreadLeg
    quantity: int
    spread_width: float
    net_quantity: float
    is_debit_spread: bool


class PositionAnalyzer:
    """Analyzes positions to identify option spreads and strategies."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def analyze_positions(self, positions: List[Position]) -> Dict[str, List]:
        """
        Analyze all positions and identify spreads.
        
        Args:
            positions: List of Position objects from portfolio
            
        Returns:
            Dictionary with spread analysis results
        """
        results = {
            'call_spreads': [],
            'put_spreads': [],
            'single_options': [],
            'stocks': [],
            'unmatched_options': []
        }
        
        # Separate positions by type
        option_positions = []
        stock_positions = []
        
        for position in positions:
            if position.instrument.type == InstrumentType.OPTION:
                option_positions.append(position)
            elif position.instrument.type == InstrumentType.EQUITY:
                stock_positions.append(position)
        
        results['stocks'] = stock_positions
        
        # Group options by underlying symbol
        options_by_underlying = self._group_options_by_underlying(option_positions)
        
        # Analyze each underlying for spreads
        for underlying, options in options_by_underlying.items():
            call_spreads, put_spreads, unmatched = self._analyze_underlying_spreads(
                underlying, options
            )
            
            results['call_spreads'].extend(call_spreads)
            results['put_spreads'].extend(put_spreads)
            results['unmatched_options'].extend(unmatched)
        
        return results
    
    def _group_options_by_underlying(self, positions: List[Position]) -> Dict[str, List[Position]]:
        """Group option positions by underlying symbol."""
        grouped = defaultdict(list)
        
        for position in positions:
            # Extract underlying symbol from option symbol
            # Assuming format like "AAPL240719C00170000"
            underlying = self._extract_underlying_from_option(position.instrument.symbol)
            if underlying:
                grouped[underlying].append(position)
        
        return dict(grouped)
    
    def _extract_underlying_from_option(self, option_symbol: str) -> Optional[str]:
        """
        Extract underlying symbol from option symbol.
        
        Example: "AAPL240719C00170000" -> "AAPL"
        """
        try:
            # Find the first digit to separate underlying from date
            for i, char in enumerate(option_symbol):
                if char.isdigit():
                    return option_symbol[:i]
            return None
        except Exception as e:
            logger.warning(f"Could not extract underlying from {option_symbol}: {e}")
            return None
    
    def _parse_option_details(self, option_symbol: str) -> Optional[Dict]:
        """
        Parse option symbol to extract details.
        
        Example: "AAPL240719C00170000" -> {
            'underlying': 'AAPL',
            'expiration': date(2024, 7, 19),
            'option_type': OptionType.CALL,
            'strike': 170.0
        }
        """
        try:
            # Extract underlying
            underlying_end = 0
            for i, char in enumerate(option_symbol):
                if char.isdigit():
                    underlying_end = i
                    break
            
            if underlying_end == 0:
                return None
            
            underlying = option_symbol[:underlying_end]
            rest = option_symbol[underlying_end:]
            
            # Extract date (YYMMDD format)
            if len(rest) < 6:
                return None
            
            date_str = rest[:6]
            year = 2000 + int(date_str[:2])
            month = int(date_str[2:4])
            day = int(date_str[4:6])
            expiration = date(year, month, day)
            
            # Extract option type (C or P)
            if len(rest) < 7:
                return None
            
            option_type_char = rest[6]
            option_type = OptionType.CALL if option_type_char == 'C' else OptionType.PUT
            
            # Extract strike price
            if len(rest) < 15:
                return None
            
            strike_str = rest[7:15]
            strike = float(strike_str) / 1000  # Strike is in thousands
            
            return {
                'underlying': underlying,
                'expiration': expiration,
                'option_type': option_type,
                'strike': strike
            }
            
        except Exception as e:
            logger.warning(f"Could not parse option symbol {option_symbol}: {e}")
            return None
    
    def _analyze_underlying_spreads(
        self, 
        underlying: str, 
        positions: List[Position]
    ) -> Tuple[List[CallSpread], List[PutSpread], List[Position]]:
        """Analyze positions for a single underlying to find spreads."""
        
        call_spreads = []
        put_spreads = []
        unmatched = []
        
        # Parse all option details
        option_legs = []
        for position in positions:
            details = self._parse_option_details(position.instrument.symbol)
            if details:
                is_long = float(position.quantity) > 0
                leg = SpreadLeg(
                    position=position,
                    symbol=position.instrument.symbol,
                    underlying=details['underlying'],
                    option_type=details['option_type'],
                    strike_price=details['strike'],
                    expiration_date=details['expiration'],
                    quantity=abs(float(position.quantity)),
                    is_long=is_long
                )
                option_legs.append(leg)
            else:
                unmatched.append(position)
        
        # Group by option type (not by expiration - allow calendar spreads)
        call_legs = []
        put_legs = []
        
        for leg in option_legs:
            if leg.option_type == OptionType.CALL:
                call_legs.append(leg)
            else:
                put_legs.append(leg)
        
        # Find call spreads (including calendar spreads)
        if call_legs:
            spreads, remaining = self._find_spreads_by_quantity_matching(call_legs, OptionType.CALL)
            call_spreads.extend(spreads)
            unmatched.extend([leg.position for leg in remaining])
        
        # Find put spreads (including calendar spreads)
        if put_legs:
            spreads, remaining = self._find_spreads_by_quantity_matching(put_legs, OptionType.PUT)
            put_spreads.extend(spreads)
            unmatched.extend([leg.position for leg in remaining])
        
        return call_spreads, put_spreads, unmatched
    
    def _find_spreads_in_legs(
        self, 
        legs: List[SpreadLeg], 
        option_type: OptionType
    ) -> Tuple[List, List[SpreadLeg]]:
        """Find spreads within legs of the same type and expiration."""
        
        spreads = []
        remaining_legs = legs.copy()
        
        # Sort legs by strike price
        legs_by_strike = defaultdict(list)
        for leg in legs:
            legs_by_strike[leg.strike_price].append(leg)
        
        # Try to match legs into spreads
        strikes = sorted(legs_by_strike.keys())
        
        for i in range(len(strikes)):
            for j in range(i + 1, len(strikes)):
                strike1, strike2 = strikes[i], strikes[j]
                legs1 = legs_by_strike[strike1]
                legs2 = legs_by_strike[strike2]
                
                # Try to find matching pairs (one long, one short)
                for leg1 in legs1.copy():
                    for leg2 in legs2.copy():
                        if leg1.is_long != leg2.is_long and leg1 in remaining_legs and leg2 in remaining_legs:
                            # Found a spread
                            if option_type == OptionType.CALL:
                                # For calls: lower strike is typically short, higher is long
                                short_leg = leg1 if leg1.strike_price < leg2.strike_price else leg2
                                long_leg = leg2 if leg1.strike_price < leg2.strike_price else leg1
                                
                                if short_leg.is_long == False and long_leg.is_long == True:
                                    spread = CallSpread(
                                        underlying=leg1.underlying,
                                        short_leg=short_leg,
                                        long_leg=long_leg,
                                        quantity=min(int(leg1.quantity), int(leg2.quantity)),
                                        spread_width=abs(long_leg.strike_price - short_leg.strike_price),
                                        net_quantity=0.0,  # TODO: Calculate based on entry prices
                                        is_debit_spread=long_leg.strike_price > short_leg.strike_price
                                    )
                                    spreads.append(spread)
                                    remaining_legs.remove(leg1)
                                    remaining_legs.remove(leg2)
                                    legs1.remove(leg1)
                                    legs2.remove(leg2)
                                    break
                            else:
                                # Similar logic for puts
                                pass
        
        return spreads, remaining_legs
    
    def _find_spreads_by_quantity_matching(
        self, 
        legs: List[SpreadLeg], 
        option_type: OptionType
    ) -> Tuple[List, List[SpreadLeg]]:
        """
        Find spreads by matching quantities of short and long positions.
        Pairs closest strikes for short and long legs.
        """
        spreads = []
        remaining_legs = legs.copy()
        
        # Separate short and long legs
        short_legs = [leg for leg in legs if not leg.is_long]
        long_legs = [leg for leg in legs if leg.is_long]
        
        # Sort by strike price for optimal pairing
        short_legs.sort(key=lambda x: x.strike_price)
        long_legs.sort(key=lambda x: x.strike_price)
        
        # Match short and long legs by quantity and closest strikes
        for short_leg in short_legs.copy():
            if short_leg not in remaining_legs:
                continue
                
            # Find the best matching long leg (closest strike)
            best_long_leg = None
            min_strike_diff = float('inf')
            
            for long_leg in long_legs:
                if long_leg not in remaining_legs:
                    continue
                
                # Check if quantities can match (we can have partial matches)
                min_quantity = min(short_leg.quantity, long_leg.quantity)
                if min_quantity <= 0:
                    continue
                
                # Calculate strike difference
                strike_diff = abs(short_leg.strike_price - long_leg.strike_price)
                
                if strike_diff < min_strike_diff:
                    min_strike_diff = strike_diff
                    best_long_leg = long_leg
            
            # Create spread if we found a matching pair
            if best_long_leg:
                min_quantity = min(short_leg.quantity, best_long_leg.quantity)
                
                if option_type == OptionType.CALL:
                    spread = CallSpread(
                        underlying=short_leg.underlying,
                        short_leg=short_leg,
                        long_leg=best_long_leg,
                        quantity=int(min_quantity),
                        spread_width=abs(best_long_leg.strike_price - short_leg.strike_price),
                        net_quantity=0.0,  # TODO: Calculate based on entry prices
                        is_debit_spread=best_long_leg.strike_price > short_leg.strike_price
                    )
                    spreads.append(spread)
                
                # Remove matched legs (or reduce quantities if partial match)
                if short_leg.quantity == min_quantity:
                    remaining_legs.remove(short_leg)
                    short_legs.remove(short_leg)
                else:
                    short_leg.quantity -= min_quantity
                
                if best_long_leg.quantity == min_quantity:
                    remaining_legs.remove(best_long_leg)
                    long_legs.remove(best_long_leg)
                else:
                    best_long_leg.quantity -= min_quantity
        
        return spreads, remaining_legs
    
    def find_call_spreads_for_symbol(self, positions: List[Position], symbol: str) -> List[CallSpread]:
        """Find all call spreads for a specific underlying symbol."""
        analysis = self.analyze_positions(positions)
        return [spread for spread in analysis['call_spreads'] if spread.underlying == symbol]
    
    def get_spread_summary(self, spread: CallSpread) -> Dict:
        """Get a summary of spread details for display."""
        # Check if it's a calendar spread (different expirations)
        is_calendar = spread.short_leg.expiration_date != spread.long_leg.expiration_date
        
        if is_calendar:
            spread_type = 'Calendar Spread'
            expiration_info = f"Short: {spread.short_leg.expiration_date}, Long: {spread.long_leg.expiration_date}"
        else:
            spread_type = 'Vertical Spread'
            expiration_info = str(spread.short_leg.expiration_date)
        
        return {
            'underlying': spread.underlying,
            'type': spread_type,
            'short_strike': spread.short_leg.strike_price,
            'long_strike': spread.long_leg.strike_price,
            'quantity': spread.quantity,
            'spread_width': spread.spread_width,
            'max_profit': spread.max_profit,
            'max_loss': spread.max_loss,
            'break_even': spread.break_even,
            'expiration': expiration_info,
            'is_calendar': is_calendar
        }
