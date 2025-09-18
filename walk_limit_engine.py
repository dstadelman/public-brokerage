"""
Walk limit order engine for executing spread orders with incremental price walking.
Clean implementation based on confirmation_card.py patterns and TASKS.md requirements.
"""

import uuid
import time
import threading
from typing import Dict, List, Optional
from datetime import datetime, date
from dataclasses import dataclass
from enum import Enum
import logging

from public_brokerage.client import PublicBrokerageClient
from public_brokerage.orders import (
    preflight_multi_leg, place_multileg_order, get_order, cancel_order
)
from public_brokerage.auth import ensure_access_token
from public_brokerage.models.order import MultiLegOrderRequest, MultiLegPreflightRequest, OrderLeg, OrderType, MultiLegPreflightResponse, OrderResponse
from public_brokerage.models.common import OrderSide, OpenCloseIndicator, InstrumentType, Instrument, Expiration, TimeInForce
from public_brokerage.models.market_data import Quote
from public_brokerage.auth import ensure_access_token
from public_brokerage.market_data import get_quotes
from config import config

logger = logging.getLogger(__name__)


class ProcessStatus(str, Enum):
    """Status of a walk limit process."""
    STARTING = "STARTING"
    RUNNING = "RUNNING" 
    WAITING = "WAITING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


@dataclass
class WalkLimitProcess:
    """Represents a walk limit trading process."""
    process_id: str
    symbol: str
    strategy: str  # 'open_call_spread' or 'close_call_spread'
    short_symbol: str  # Actual option symbol
    long_symbol: str   # Actual option symbol
    quantity: int
    remaining_quantity: int  # Track unfilled quantity for partial fills
    max_wait_time: int
    execute_mode: bool
    status: ProcessStatus
    current_price: float
    target_price: float
    increment: float
    attempts: int
    max_attempts: int
    created_at: datetime
    last_update: datetime
    last_order_id: Optional[str] = None


class WalkLimitEngine:
    """Manages walk limit order processes for option spreads."""
    
    def __init__(self, client: PublicBrokerageClient):
        self.client = client
        self.logger = logging.getLogger(__name__)
        self.processes: Dict[str, WalkLimitProcess] = {}
        self.threads: Dict[str, threading.Thread] = {}
        self.stop_events: Dict[str, threading.Event] = {}
    
    def start_open_call_spread_process(
        self,
        symbol: str,
        short_expiration: str,
        short_strike: float,
        long_expiration: str,
        long_strike: float,
        quantity: int,
        account_id: str,
        max_wait_time: int = 42,
        execute_mode: bool = False
    ) -> str:
        """Start walk limit process to open a call spread."""
        
        # Construct option symbols using the same pattern as confirmation_card.py
        short_symbol = self._construct_option_symbol(symbol, short_expiration, short_strike)
        long_symbol = self._construct_option_symbol(symbol, long_expiration, long_strike)
        
        # Get current spread pricing
        spread_bid, spread_ask = self._get_spread_pricing(short_symbol, long_symbol, account_id)
        
        if spread_bid is None or spread_ask is None:
            raise ValueError("Could not determine spread pricing")
        
        # Calculate increment size based on TASKS.md
        spread_width = spread_ask - spread_bid
        if spread_width >= 0.20:
            increment = round(spread_width / 20, 2)  # Round to penny
        else:
            increment = 0.01
        
        # Ensure minimum penny increment
        increment = max(0.01, increment)
        
        max_attempts = int(spread_width / increment) + 1
        
        # Create process
        process_id = str(uuid.uuid4())[:8]
        process = WalkLimitProcess(
            process_id=process_id,
            symbol=symbol,
            strategy="open_call_spread",
            short_symbol=short_symbol,
            long_symbol=long_symbol,
            quantity=quantity,
            remaining_quantity=quantity,  # Initially all quantity is remaining
            max_wait_time=max_wait_time,
            execute_mode=execute_mode,
            status=ProcessStatus.STARTING,
            current_price=round(spread_bid + increment, 2),  # Start one increment above bid (penny pricing)
            target_price=round(spread_ask, 2),   # Walk up to ask (penny pricing)
            increment=increment,
            attempts=0,
            max_attempts=max_attempts,
            created_at=datetime.now(),
            last_update=datetime.now()
        )
        
        self.processes[process_id] = process
        
        # Start background thread
        stop_event = threading.Event()
        self.stop_events[process_id] = stop_event
        
        thread = threading.Thread(
            target=self._run_open_spread_process,
            args=(process, stop_event, account_id),
            daemon=True
        )
        self.threads[process_id] = thread
        thread.start()
        
        self.logger.info(f"Started open call spread process {process_id} for {symbol}")
        return process_id
    
    def start_close_call_spread_process(
        self,
        symbol: str,
        spreads: List,  # List of CallSpread objects
        account_id: str,
        max_wait_time: int = 42,
        execute_mode: bool = False
    ) -> List[str]:
        """Start walk limit processes to close call spreads."""
        process_ids = []
        
        for spread in spreads:
            # Use actual symbols from the spread positions - clean format like confirmation card
            short_symbol = spread.short_leg.symbol.replace('-OPTION', '')
            long_symbol = spread.long_leg.symbol.replace('-OPTION', '')
            
            # Get current spread pricing
            spread_bid, spread_ask = self._get_spread_pricing(short_symbol, long_symbol, account_id)
            
            if spread_bid is None or spread_ask is None:
                self.logger.error(f"Could not determine pricing for {symbol} spread")
                continue
            
            # Calculate increment size based on TASKS.md
            spread_width = spread_ask - spread_bid
            if spread_width >= 0.20:
                increment = round(spread_width / 20, 2)  # Round to penny
            else:
                increment = 0.01
            
            # Ensure minimum penny increment
            increment = max(0.01, increment)
            
            max_attempts = int(spread_width / increment) + 1
            
            # Create process
            process_id = str(uuid.uuid4())[:8]
            process = WalkLimitProcess(
                process_id=process_id,
                symbol=symbol,
                strategy="close_call_spread",
                short_symbol=short_symbol,
                long_symbol=long_symbol,
                quantity=spread.quantity,
                remaining_quantity=spread.quantity,  # Initially all quantity is remaining
                max_wait_time=max_wait_time,
                execute_mode=execute_mode,
                status=ProcessStatus.STARTING,
                current_price=round(spread_ask - increment, 2),  # Start one increment below ask for closing (positive internally)
                target_price=round(spread_bid, 2),   # Walk down to bid (positive internally)
                increment=-increment,      # Negative increment for walking down
                attempts=0,
                max_attempts=max_attempts,
                created_at=datetime.now(),
                last_update=datetime.now()
            )
            
            self.processes[process_id] = process
            
            # Start background thread
            stop_event = threading.Event()
            self.stop_events[process_id] = stop_event
            
            thread = threading.Thread(
                target=self._run_close_spread_process,
                args=(process, stop_event, account_id),
                daemon=True
            )
            self.threads[process_id] = thread
            thread.start()
            
            process_ids.append(process_id)
            self.logger.info(f"Started close call spread process {process_id} for {symbol}")
        
        return process_ids
    
    def _construct_option_symbol(self, underlying: str, expiration: str, strike: float) -> str:
        """Construct option symbol using standardized OSI format"""
        from utils import format_osi_symbol
        
        # Use the standardized OSI formatter for call options
        return format_osi_symbol(underlying, expiration, "C", strike)
    
    def _get_spread_pricing(self, short_symbol: str, long_symbol: str, account_id: str) -> tuple[Optional[float], Optional[float]]:
        """Get current bid/ask pricing for a spread using the same method as confirmation_card.py"""
        try:
            self.logger.info(f"Getting quotes for short: {short_symbol}, long: {long_symbol}")
            
            # Create instrument objects exactly like confirmation_card.py
            short_instrument = Instrument(symbol=short_symbol, type=InstrumentType.OPTION)
            long_instrument = Instrument(symbol=long_symbol, type=InstrumentType.OPTION)
            
            # Get quotes
            quotes = get_quotes(self.client, account_id, [short_instrument, long_instrument])
            
            if len(quotes) != 2:
                self.logger.error(f"Expected 2 quotes, got {len(quotes)}")
                return None, None
            
            short_quote = quotes[0]
            long_quote = quotes[1]
            
            # Check if we have missing bid/ask data for either quote
            short_has_data = short_quote.bid is not None and short_quote.ask is not None
            long_has_data = long_quote.bid is not None and long_quote.ask is not None
            
            # If either quote is missing data, try to get it from the option chain
            if not short_has_data or not long_has_data:
                self.logger.warning("Missing bid/ask data in quotes, attempting fallback to option chain")
                
                # Try to get missing quotes from option chain
                if not short_has_data:
                    short_quote = self._get_quote_from_chain(short_symbol, account_id)
                if not long_has_data:
                    long_quote = self._get_quote_from_chain(long_symbol, account_id)
                
                # Re-check if we now have valid data
                if not (short_quote and long_quote and 
                        short_quote.bid is not None and short_quote.ask is not None and
                        long_quote.bid is not None and long_quote.ask is not None):
                    self.logger.error("Still missing bid/ask data after fallback attempts")
                    return None, None
            
            # Calculate spread pricing exactly like confirmation_card.py does for closing spreads
            # Convert to float like confirmation_card.py does
            spread_bid = float(long_quote.bid) - float(short_quote.ask)  # What we receive for closing
            spread_ask = float(long_quote.ask) - float(short_quote.bid)  # What we pay for closing
            
            self.logger.info(f"Spread pricing: {spread_bid:.2f} / {spread_ask:.2f}")
            return spread_bid, spread_ask
            
        except Exception as e:
            self.logger.error(f"Error getting spread pricing: {e}")
            return None, None
    
    def _get_quote_from_chain(self, option_symbol: str, account_id: str) -> Optional[Quote]:
        """
        Get quote for a specific option by searching the option chain.
        This is a fallback when direct quote API fails.
        """
        try:
            from public_brokerage.market_data import get_option_chain
            from utils.option_symbols import parse_osi_symbol
            
            # Parse option symbol using the existing utility function
            try:
                parsed = parse_osi_symbol(option_symbol)
                underlying = parsed['underlying']
                exp_date_str = parsed['expiration_date']
                option_type = parsed['option_type']
                strike = parsed['strike_price']
                
                # Convert expiration date string to date object
                exp_date = datetime.strptime(exp_date_str, '%Y-%m-%d').date()
                
            except Exception as e:
                self.logger.error(f"Could not parse option symbol {option_symbol}: {e}")
                return None
            
            # Create underlying instrument
            underlying_instrument = Instrument(symbol=underlying, type=InstrumentType.EQUITY)
            
            # Get option chain
            chain = get_option_chain(self.client, account_id, underlying_instrument, exp_date)
            
            # Search for our specific option in the chain
            options_to_search = chain.calls if option_type == 'C' else chain.puts
            
            for option in options_to_search:
                if option.instrument.symbol == option_symbol and option.outcome == "SUCCESS":
                    self.logger.info(f"Found quote for {option_symbol} in option chain: bid={option.bid}, ask={option.ask}")
                    return option
            
            self.logger.warning(f"Option {option_symbol} not found in option chain")
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting quote from chain for {option_symbol}: {e}")
            return None
    
    def _run_open_spread_process(self, process: WalkLimitProcess, stop_event: threading.Event, account_id: str):
        """Run the walk limit process for opening a spread."""
        try:
            process.status = ProcessStatus.RUNNING
            
            while not stop_event.is_set() and process.attempts < process.max_attempts:
                try:
                    # Safety check: stop if no remaining quantity
                    if process.remaining_quantity <= 0:
                        self.logger.info(f"[COMPLETE] Process {process.process_id} - all contracts filled")
                        process.status = ProcessStatus.COMPLETED
                        return
                    
                    # Check if we've reached target
                    if process.current_price > process.target_price:
                        self.logger.info(f"Process {process.process_id} reached target price")
                        break
                    
                    # Create and preflight order
                    preflight_request = self._create_open_spread_preflight(process, account_id)
                    if not preflight_request:
                        self._emergency_stop_process(process, account_id, "Failed to create preflight request")
                        return
                    
                    # Print preflight details - handle Pydantic model format
                    if isinstance(preflight_request, MultiLegPreflightRequest):
                        limit_price = float(preflight_request.limitPrice)
                        legs = preflight_request.legs
                        quantity = preflight_request.quantity
                        self.logger.info(f"[PREFLIGHT] Preflight details: {len(legs)} legs, quantity: {quantity}, limit: ${limit_price:.2f}")
                        for i, leg in enumerate(legs):
                            side_str = leg.side if isinstance(leg.side, str) else leg.side.value
                            open_str = leg.openCloseIndicator if isinstance(leg.openCloseIndicator, str) else leg.openCloseIndicator.value
                            self.logger.info(f"   Leg {i+1}: {side_str} {leg.ratioQuantity} {leg.instrument.symbol} ({open_str})")
                    
                    # Preflight the order
                    try:
                        preflight_result = preflight_multi_leg(self.client, account_id, preflight_request)
                    except Exception as preflight_error:
                        self._emergency_stop_process(process, account_id, f"Preflight API error: {preflight_error}")
                        return
                    
                    if preflight_result is None or hasattr(preflight_result, 'errorMessage'):
                        error_msg = getattr(preflight_result, 'errorMessage', 'Unknown error') if preflight_result else 'API request failed'
                        self._emergency_stop_process(process, account_id, f"Preflight failed: {error_msg}")
                        return
                    
                    self.logger.info(f"Preflight successful for process {process.process_id} at ${process.current_price:.2f}")
                    
                    # Log preflight response details
                    if hasattr(preflight_result, 'estimatedCommission'):
                        self.logger.info(f"[PREFLIGHT] Commission: ${preflight_result.estimatedCommission}")
                    if hasattr(preflight_result, 'orderValue'):
                        self.logger.info(f"[PREFLIGHT] Order Value: ${preflight_result.orderValue}")
                    if hasattr(preflight_result, 'buyingPowerRequirement'):
                        self.logger.info(f"[PREFLIGHT] Buying Power Required: ${preflight_result.buyingPowerRequirement}")
                    
                    if process.execute_mode:
                        # Create actual order request (different from preflight)
                        import uuid
                        order_id = str(uuid.uuid4())
                        order_request = self._create_open_spread_order(process, account_id, order_id)
                        if not order_request:
                            self._emergency_stop_process(process, account_id, "Failed to create order request")
                            return
                        
                        # Place the actual order using remaining quantity
                        try:
                            order_id = place_multileg_order(self.client, account_id, order_request)
                        except Exception as order_error:
                            self._emergency_stop_process(process, account_id, f"Order placement error: {order_error}")
                            return
                            
                        if order_id:  # If we got an order ID, the order was successful
                            process.last_order_id = order_id
                            self.logger.info(f"[ORDER] Placed order {order_id} for {process.remaining_quantity} contracts at ${process.current_price:.2f}")
                            
                            # Wait for fill or timeout with partial fill handling
                            try:
                                is_complete = self._wait_for_fill_with_partial_handling(process, stop_event, account_id)
                            except Exception as fill_error:
                                self._emergency_stop_process(process, account_id, f"Fill monitoring error: {fill_error}")
                                return
                            
                            # If completely filled, we're done
                            if is_complete:
                                process.status = ProcessStatus.COMPLETED
                                self.logger.info(f"[SUCCESS] Process {process.process_id} completed successfully - all {process.quantity} contracts filled")
                                return
                            
                            # Cancel any unfilled portion and get the actual filled quantity
                            if process.last_order_id:
                                try:
                                    cancel_success, filled_qty = self._cancel_order_with_verification(process, account_id)
                                    if not cancel_success:
                                        self.logger.warning(f"[CANCEL] Order {process.last_order_id} could not be cancelled - may have filled during cancel")
                                    
                                    # Update remaining quantity based on actual fills from cancel verification
                                    if filled_qty > 0:
                                        process.remaining_quantity -= filled_qty
                                        self.logger.info(f"[PROGRESS] Filled {filled_qty} contracts during timeout/cancel, {process.remaining_quantity} remaining")
                                    
                                    # Check if we're now complete after getting filled quantity from cancel
                                    if process.remaining_quantity <= 0:
                                        process.status = ProcessStatus.COMPLETED
                                        self.logger.info(f"[SUCCESS] Process {process.process_id} completed successfully - all {process.quantity} contracts filled")
                                        return
                                except Exception as cancel_error:
                                    self._emergency_stop_process(process, account_id, f"CRITICAL cancellation error: {cancel_error}")
                                    return
                        else:
                            self._emergency_stop_process(process, account_id, "Order placement returned no order ID")
                            return
                    else:
                        # Dry run - just log what would happen and use short timeout
                        self.logger.info(f"DRY RUN: Would place order for {process.remaining_quantity} contracts at ${process.current_price:.2f}")
                        time.sleep(1)  # Brief pause for dry run - use 1 second instead of max_wait_time
                    
                    # Move to next price level
                    process.current_price = round(process.current_price + process.increment, 2)  # Round to penny
                    process.attempts += 1
                    process.last_update = datetime.now()
                    
                except Exception as loop_error:
                    self._emergency_stop_process(process, account_id, f"Loop iteration error: {loop_error}")
                    return
            
            process.status = ProcessStatus.COMPLETED
            
        except Exception as e:
            self._emergency_stop_process(process, account_id, f"Process error: {e}")
    
    def _run_close_spread_process(self, process: WalkLimitProcess, stop_event: threading.Event, account_id: str):
        """Run the walk limit process for closing a spread."""
        try:
            process.status = ProcessStatus.RUNNING
            self.logger.info(f"[WALK] Starting close spread walk limit for {process.symbol}")
            self.logger.info(f"[PRICE] Price range: ${process.current_price:.2f} (ask) -> ${process.target_price:.2f} (bid)")
            self.logger.info(f"[INCREMENT] Increment: ${abs(process.increment):.2f}, Max attempts: {process.max_attempts}")
            
            while not stop_event.is_set() and process.attempts < process.max_attempts:
                try:
                    # Safety check: stop if no remaining quantity
                    if process.remaining_quantity <= 0:
                        self.logger.info(f"[COMPLETE] Process {process.process_id} - all contracts filled")
                        process.status = ProcessStatus.COMPLETED
                        return
                    
                    # Check if we've reached target
                    if process.current_price < process.target_price:
                        self.logger.info(f"[TARGET] Process {process.process_id} reached target bid price ${process.target_price:.2f}")
                        break
                    
                    # Create and preflight order
                    self.logger.info(f"[ATTEMPT] Attempt {process.attempts + 1}/{process.max_attempts}: Testing order at ${process.current_price:.2f}")
                    preflight_request = self._create_close_spread_preflight(process, account_id)
                    if not preflight_request:
                        self._emergency_stop_process(process, account_id, "Failed to create close spread preflight request")
                        return
                    
                    # Print preflight details - handle Pydantic model format
                    if isinstance(preflight_request, MultiLegPreflightRequest):
                        limit_price = float(preflight_request.limitPrice)
                        legs = preflight_request.legs
                        quantity = preflight_request.quantity
                        self.logger.info(f"[PREFLIGHT] Preflight details: {len(legs)} legs, quantity: {quantity}, limit: ${limit_price:.2f}")
                        for i, leg in enumerate(legs):
                            side_str = leg.side if isinstance(leg.side, str) else leg.side.value
                            close_str = leg.openCloseIndicator if isinstance(leg.openCloseIndicator, str) else leg.openCloseIndicator.value
                            self.logger.info(f"   Leg {i+1}: {side_str} {leg.ratioQuantity} {leg.instrument.symbol} ({close_str})")
                    
                    # Debug: Log the preflight request data
                    self.logger.info(f"[DEBUG] Preflight request data: {preflight_request}")
                    
                    # Preflight the order
                    try:
                        preflight_result = preflight_multi_leg(self.client, account_id, preflight_request)
                    except Exception as preflight_error:
                        self._emergency_stop_process(process, account_id, f"Close spread preflight API error: {preflight_error}")
                        return
                    
                    if preflight_result is None or hasattr(preflight_result, 'errorMessage'):
                        error_msg = getattr(preflight_result, 'errorMessage', 'Unknown error') if preflight_result else 'API request failed'
                        self._emergency_stop_process(process, account_id, f"Close spread preflight failed: {error_msg}")
                        return
                    
                    self.logger.info(f"[PREFLIGHT] Preflight successful for process {process.process_id} at ${process.current_price:.2f}")
                    
                    # Log the ENTIRE preflight response for debugging
                    self.logger.info(f"[PREFLIGHT] FULL RESPONSE: {preflight_result}")
                    self.logger.info(f"[PREFLIGHT] RESPONSE TYPE: {type(preflight_result)}")
                    self.logger.info(f"[PREFLIGHT] RESPONSE DICT: {preflight_result.__dict__ if hasattr(preflight_result, '__dict__') else 'No __dict__'}")
                    
                    # Log all the preflight response details
                    if hasattr(preflight_result, 'baseSymbol'):
                        self.logger.info(f"[PREFLIGHT] Base Symbol: {preflight_result.baseSymbol}")
                    if hasattr(preflight_result, 'strategyName'):
                        self.logger.info(f"[PREFLIGHT] Strategy: {preflight_result.strategyName}")
                    if hasattr(preflight_result, 'estimatedCost'):
                        self.logger.info(f"[PREFLIGHT] Estimated Cost: ${preflight_result.estimatedCost}")
                    if hasattr(preflight_result, 'estimatedProceeds'):
                        self.logger.info(f"[PREFLIGHT] Estimated Proceeds: ${preflight_result.estimatedProceeds}")
                    if hasattr(preflight_result, 'orderValue'):
                        self.logger.info(f"[PREFLIGHT] Order Value: ${preflight_result.orderValue}")
                    if hasattr(preflight_result, 'estimatedCommission'):
                        self.logger.info(f"[PREFLIGHT] Commission: ${preflight_result.estimatedCommission}")
                    if hasattr(preflight_result, 'buyingPowerRequirement'):
                        self.logger.info(f"[PREFLIGHT] Buying Power Required: ${preflight_result.buyingPowerRequirement}")
                    
                    # Log regulatory fees if present
                    if hasattr(preflight_result, 'regulatoryFees') and preflight_result.regulatoryFees:
                        fees = preflight_result.regulatoryFees
                        self.logger.info(f"[PREFLIGHT] Regulatory Fees: SEC=${getattr(fees, 'secFee', 'N/A')}, TAF=${getattr(fees, 'tafFee', 'N/A')}, OCC=${getattr(fees, 'occFee', 'N/A')}")
                    
                    # Log margin impact if present
                    if hasattr(preflight_result, 'marginImpact') and preflight_result.marginImpact:
                        margin = preflight_result.marginImpact
                        self.logger.info(f"[PREFLIGHT] Margin Impact: Usage=${getattr(margin, 'marginUsageImpact', 'N/A')}, Initial=${getattr(margin, 'initialMarginRequirement', 'N/A')}")
                    
                    # Log price increment info if present
                    if hasattr(preflight_result, 'priceIncrement') and preflight_result.priceIncrement:
                        increment = preflight_result.priceIncrement
                        self.logger.info(f"[PREFLIGHT] Price Increments: Below $3=${getattr(increment, 'incrementBelow3', 'N/A')}, Above $3=${getattr(increment, 'incrementAbove3', 'N/A')}, Current=${getattr(increment, 'currentIncrement', 'N/A')}")
                    
                    # Summary line showing the key financial impact
                    cost = getattr(preflight_result, 'estimatedCost', 'N/A')
                    proceeds = getattr(preflight_result, 'estimatedProceeds', 'N/A')
                    commission = getattr(preflight_result, 'estimatedCommission', 'N/A')
                    self.logger.info(f"[PREFLIGHT] SUMMARY: Cost=${cost}, Proceeds=${proceeds}, Commission=${commission}")
                    
                    if process.execute_mode:
                        # Create actual order request (different from preflight)
                        import uuid
                        order_id = str(uuid.uuid4())
                        order_request = self._create_close_spread_order(process, account_id, order_id)
                        if not order_request:
                            self._emergency_stop_process(process, account_id, "Failed to create close spread order request")
                            return
                        
                        # Place the actual order using remaining quantity
                        try:
                            order_id = place_multileg_order(self.client, account_id, order_request)
                        except Exception as order_error:
                            self._emergency_stop_process(process, account_id, f"Close spread order placement error: {order_error}")
                            return
                            
                        if order_id:  # If we got an order ID, the order was successful
                            process.last_order_id = order_id
                            self.logger.info(f"[ORDER] Placed order {order_id} for {process.remaining_quantity} contracts at ${process.current_price:.2f}")
                            
                            # Wait for fill or timeout with partial fill handling
                            try:
                                is_complete = self._wait_for_fill_with_partial_handling(process, stop_event, account_id)
                            except Exception as fill_error:
                                self._emergency_stop_process(process, account_id, f"Close spread fill monitoring error: {fill_error}")
                                return
                            
                            # If completely filled, we're done
                            if is_complete:
                                process.status = ProcessStatus.COMPLETED
                                self.logger.info(f"[SUCCESS] Process {process.process_id} completed successfully - all {process.quantity} contracts filled")
                                return
                            
                            # Cancel any unfilled portion and get the actual filled quantity
                            if process.last_order_id:
                                try:
                                    cancel_success, filled_qty = self._cancel_order_with_verification(process, account_id)
                                    if not cancel_success:
                                        self.logger.warning(f"[CANCEL] Order {process.last_order_id} could not be cancelled - may have filled during cancel")
                                    
                                    # Update remaining quantity based on actual fills from cancel verification
                                    if filled_qty > 0:
                                        process.remaining_quantity -= filled_qty
                                        self.logger.info(f"[PROGRESS] Filled {filled_qty} contracts during timeout/cancel, {process.remaining_quantity} remaining")
                                    
                                    # Check if we're now complete after getting filled quantity from cancel
                                    if process.remaining_quantity <= 0:
                                        process.status = ProcessStatus.COMPLETED
                                        self.logger.info(f"[SUCCESS] Process {process.process_id} completed successfully - all {process.quantity} contracts filled")
                                        return
                                except Exception as cancel_error:
                                    self._emergency_stop_process(process, account_id, f"CRITICAL cancellation error: {cancel_error}")
                                    return
                        else:
                            self._emergency_stop_process(process, account_id, "Close spread order placement returned no order ID")
                            return
                    else:
                        # Dry run - just log what would happen and use short timeout
                        self.logger.info(f"DRY RUN: Would place order for {process.remaining_quantity} contracts at ${process.current_price:.2f}")
                        time.sleep(1)  # Brief pause for dry run - use 1 second instead of max_wait_time
                    
                    # Move to next price level (walking down for closing)
                    next_price = round(process.current_price + process.increment, 2)  # increment is negative for closing, round to penny
                    self.logger.info(f"[WALK] Walking price down from ${process.current_price:.2f} to ${next_price:.2f}")
                    process.current_price = next_price
                    process.attempts += 1
                    process.last_update = datetime.now()
                    
                except Exception as loop_error:
                    self._emergency_stop_process(process, account_id, f"Close spread loop iteration error: {loop_error}")
                    return
            
            process.status = ProcessStatus.COMPLETED
            
        except Exception as e:
            self._emergency_stop_process(process, account_id, f"Close spread process error: {e}")
    
    def _create_open_spread_preflight(self, process: WalkLimitProcess, account_id: str) -> Optional[MultiLegPreflightRequest]:
        """Create multi-leg preflight request for opening a spread."""
        try:
            # Create legs following the Pydantic pattern
            legs = []
            
            # Short leg (sell call)
            short_leg = OrderLeg(
                instrument=Instrument(symbol=process.short_symbol, type=InstrumentType.OPTION),
                side=OrderSide.SELL,
                openCloseIndicator=OpenCloseIndicator.OPEN,
                ratioQuantity=1  # Always 1 for ratio
            )
            legs.append(short_leg)
            
            # Long leg (buy call)
            long_leg = OrderLeg(
                instrument=Instrument(symbol=process.long_symbol, type=InstrumentType.OPTION),
                side=OrderSide.BUY,
                openCloseIndicator=OpenCloseIndicator.OPEN,
                ratioQuantity=1  # Always 1 for ratio
            )
            legs.append(long_leg)
            
            # Create preflight request (uses orderType, str quantity, no orderId)
            expiration = Expiration(timeInForce=TimeInForce.DAY)
            return MultiLegPreflightRequest(
                quantity=str(process.remaining_quantity),  # str for preflight
                orderType=OrderType.LIMIT,  # orderType for preflight
                limitPrice=str(process.current_price),
                expiration=expiration,
                legs=legs
            )
            
        except Exception as e:
            self.logger.error(f"Error creating open spread preflight: {e}")
            return None
    
    def _create_open_spread_order(self, process: WalkLimitProcess, account_id: str, order_id: str) -> Optional[MultiLegOrderRequest]:
        """Create multi-leg order for opening a spread."""
        try:
            # Create legs following the Pydantic pattern
            legs = []
            
            # Short leg (sell call)
            short_leg = OrderLeg(
                instrument=Instrument(symbol=process.short_symbol, type=InstrumentType.OPTION),
                side=OrderSide.SELL,
                openCloseIndicator=OpenCloseIndicator.OPEN,
                ratioQuantity=1  # Always 1 for ratio
            )
            legs.append(short_leg)
            
            # Long leg (buy call)
            long_leg = OrderLeg(
                instrument=Instrument(symbol=process.long_symbol, type=InstrumentType.OPTION),
                side=OrderSide.BUY,
                openCloseIndicator=OpenCloseIndicator.OPEN,
                ratioQuantity=1  # Always 1 for ratio
            )
            legs.append(long_leg)
            
            # Create order request (uses type, str quantity, requires orderId)
            expiration = Expiration(timeInForce=TimeInForce.DAY)
            return MultiLegOrderRequest(
                orderId=order_id,  # Required for orders
                quantity=str(process.remaining_quantity),  # str for orders
                type=OrderType.LIMIT,  # type for orders
                limitPrice=str(process.current_price),
                expiration=expiration,
                legs=legs
            )
            
        except Exception as e:
            self.logger.error(f"Error creating open spread order: {e}")
            return None
    
    def _create_close_spread_preflight(self, process: WalkLimitProcess, account_id: str) -> Optional[MultiLegPreflightRequest]:
        """Create multi-leg preflight request for closing a spread."""
        try:
            # Create legs following the Pydantic pattern
            legs = []
            
            # Short leg (buy to close)
            short_leg = OrderLeg(
                instrument=Instrument(symbol=process.short_symbol, type=InstrumentType.OPTION),
                side=OrderSide.BUY,
                openCloseIndicator=OpenCloseIndicator.CLOSE,
                ratioQuantity=1  # Always 1 for ratio
            )
            legs.append(short_leg)
            
            # Long leg (sell to close)
            long_leg = OrderLeg(
                instrument=Instrument(symbol=process.long_symbol, type=InstrumentType.OPTION),
                side=OrderSide.SELL,
                openCloseIndicator=OpenCloseIndicator.CLOSE,
                ratioQuantity=1  # Always 1 for ratio
            )
            legs.append(long_leg)
            
            # Create preflight request (uses orderType, str quantity, no orderId)
            expiration = Expiration(timeInForce=TimeInForce.DAY)
            return MultiLegPreflightRequest(
                quantity=str(process.remaining_quantity),  # str for preflight
                orderType=OrderType.LIMIT,  # orderType for preflight
                limitPrice=str(-process.current_price),  # Negative for closing (we want credit)
                expiration=expiration,
                legs=legs
            )
            
        except Exception as e:
            self.logger.error(f"Error creating close spread preflight: {e}")
            return None

    def _create_close_spread_order(self, process: WalkLimitProcess, account_id: str, order_id: str) -> Optional[MultiLegOrderRequest]:
        """Create multi-leg order for closing a spread."""
        try:
            # Create legs following the Pydantic pattern
            legs = []
            
            # Short leg (buy to close)
            short_leg = OrderLeg(
                instrument=Instrument(symbol=process.short_symbol, type=InstrumentType.OPTION),
                side=OrderSide.BUY,
                openCloseIndicator=OpenCloseIndicator.CLOSE,
                ratioQuantity=1  # Always 1 for ratio
            )
            legs.append(short_leg)
            
            # Long leg (sell to close)
            long_leg = OrderLeg(
                instrument=Instrument(symbol=process.long_symbol, type=InstrumentType.OPTION),
                side=OrderSide.SELL,
                openCloseIndicator=OpenCloseIndicator.CLOSE,
                ratioQuantity=1  # Always 1 for ratio
            )
            legs.append(long_leg)
            
            # Create order request (uses type, int quantity, requires orderId)
            expiration = Expiration(timeInForce=TimeInForce.DAY)
            return MultiLegOrderRequest(
                orderId=order_id,  # Required for orders
                quantity=process.remaining_quantity,  # int for orders
                type=OrderType.LIMIT,  # type for orders
                limitPrice=str(-process.current_price),  # Negative for closing (we want credit)
                expiration=expiration,
                legs=legs
            )
            
        except Exception as e:
            self.logger.error(f"Error creating close spread order: {e}")
            return None


    def _wait_for_fill_with_partial_handling(self, process: WalkLimitProcess, stop_event: threading.Event, account_id: str) -> bool:
        """
        Wait for order to fill or timeout, handling partial fills.
        
        Returns:
            bool: True if fully filled before timeout, False if partial/unfilled/timeout
        """
        if not process.last_order_id:
            return False
        
        start_time = time.time()
        while time.time() - start_time < process.max_wait_time:
            if stop_event.is_set():
                return False
            
            try:
                order_status = get_order(self.client, account_id, process.last_order_id)
                
                # Get filled quantity (default to 0 if not available)
                filled_qty = int(float(order_status.filledQuantity)) if hasattr(order_status, 'filledQuantity') and order_status.filledQuantity else 0
                
                if order_status.status == 'FILLED':
                    self.logger.info(f"[FILL] Order {process.last_order_id} fully filled: {filled_qty} contracts")
                    return True  # Complete fill
                elif order_status.status == 'PARTIALLY_FILLED':
                    self.logger.info(f"[PARTIAL] Order {process.last_order_id} partially filled: {filled_qty}/{process.remaining_quantity} contracts - continuing to wait for remainder")
                    # Continue waiting - don't return yet, let the full timeout run
                elif order_status.status in ['CANCELLED', 'REJECTED']:
                    self.logger.info(f"[STATUS] Order {process.last_order_id} status: {order_status.status}")
                    return False  # No more fills possible
                    
            except Exception as e:
                self.logger.error(f"Error checking order status: {e}")
            
            time.sleep(10)  # Wait 10 seconds before next API call to reduce API load
        
        # Timeout - check final status for any complete fill
        try:
            order_status = get_order(self.client, account_id, process.last_order_id)
            filled_qty = int(float(order_status.filledQuantity)) if hasattr(order_status, 'filledQuantity') and order_status.filledQuantity else 0
            
            if order_status.status == 'FILLED':
                self.logger.info(f"[FILL] Order {process.last_order_id} completed just before timeout: {filled_qty} contracts")
                return True  # Complete fill at the last moment!
            else:
                self.logger.info(f"[TIMEOUT] Order {process.last_order_id} timeout - will cancel and check fills")
                return False
        except Exception as e:
            self.logger.error(f"Error checking final order status: {e}")
            return False

    def _emergency_stop_process(self, process: WalkLimitProcess, account_id: str, error_msg: str):
        """
        Emergency stop for a process - cancel all orders and mark as error.
        
        Args:
            process: The process to stop
            account_id: Account ID for order cancellation
            error_msg: Error message to log
        """
        self.logger.error(f"[EMERGENCY STOP] Process {process.process_id}: {error_msg}")
        process.status = ProcessStatus.ERROR
        
        # Cancel any pending order
        if process.last_order_id:
            try:
                self.logger.warning(f"[EMERGENCY] Cancelling order {process.last_order_id}")
                cancel_order(self.client, account_id, process.last_order_id)
                
                # Quick verification (reduced timeout for emergency)
                for attempt in range(5):  # Only 5 attempts in emergency
                    try:
                        order_status = get_order(self.client, account_id, process.last_order_id)
                        if order_status.status in ['CANCELLED', 'REJECTED']:
                            self.logger.info(f"[EMERGENCY] Order {process.last_order_id} successfully cancelled")
                            break
                        elif order_status.status in ['FILLED', 'PARTIALLY_FILLED']:
                            self.logger.warning(f"[EMERGENCY] Order {process.last_order_id} filled before cancel! Status: {order_status.status}")
                            break
                        time.sleep(0.5)  # Shorter delay in emergency
                    except Exception as cancel_check_error:
                        self.logger.error(f"[EMERGENCY] Error checking cancel status: {cancel_check_error}")
                        time.sleep(0.5)
                else:
                    self.logger.error(f"[EMERGENCY] Could not verify cancellation of order {process.last_order_id}")
                    
            except Exception as cancel_error:
                self.logger.error(f"[EMERGENCY] Failed to cancel order {process.last_order_id}: {cancel_error}")

    def _cancel_order_with_verification(self, process: WalkLimitProcess, account_id: str) -> tuple[bool, int]:
        """
        Cancel order and verify it was actually cancelled.
        
        Returns:
            tuple[bool, int]: (cancel_success, filled_quantity)
            - cancel_success: True if successfully cancelled, False otherwise
            - filled_quantity: Number of contracts that were filled before/during cancellation
        """
        if not process.last_order_id:
            return True, 0  # No order to cancel
            
        try:
            # Send cancel request
            self.logger.info(f"[CANCEL] Cancelling order {process.last_order_id}")
            cancel_order(self.client, account_id, process.last_order_id)
            
            # Verify cancellation with retries
            max_cancel_checks = 10  # Up to 10 seconds
            for attempt in range(max_cancel_checks):
                try:
                    order_status = get_order(self.client, account_id, process.last_order_id)
                    filled_qty = int(float(order_status.filledQuantity)) if hasattr(order_status, 'filledQuantity') and order_status.filledQuantity else 0
                    
                    if order_status.status in ['CANCELLED']:
                        self.logger.info(f"[CANCEL] Order {process.last_order_id} successfully cancelled - filled quantity: {filled_qty}")
                        return True, filled_qty
                    elif order_status.status in ['FILLED', 'PARTIALLY_FILLED']:
                        self.logger.warning(f"[CANCEL] Order {process.last_order_id} filled during cancel attempt! Status: {order_status.status}, filled: {filled_qty}")
                        return False, filled_qty  # Order filled before we could cancel
                    elif order_status.status in ['REJECTED']:
                        self.logger.info(f"[CANCEL] Order {process.last_order_id} was rejected (counts as cancelled) - filled quantity: {filled_qty}")
                        return True, filled_qty
                    
                    # Still pending cancellation
                    self.logger.debug(f"[CANCEL] Attempt {attempt + 1}: Order {process.last_order_id} status: {order_status.status}")
                    time.sleep(1)
                    
                except Exception as e:
                    self.logger.error(f"Error checking cancel status (attempt {attempt + 1}): {e}")
                    time.sleep(1)
            
            # If we get here, cancel verification timed out - CRITICAL ERROR
            try:
                order_status = get_order(self.client, account_id, process.last_order_id)
                filled_qty = int(float(order_status.filledQuantity)) if hasattr(order_status, 'filledQuantity') and order_status.filledQuantity else 0
                self.logger.error(f"[CANCEL] CRITICAL: Failed to verify cancellation of order {process.last_order_id} after {max_cancel_checks} attempts - final filled quantity: {filled_qty}")
                # This is a critical race condition - we don't know if order is cancelled or not
                raise Exception(f"CRITICAL: Cannot verify cancellation status of order {process.last_order_id} - race condition risk! Final filled: {filled_qty}")
            except Exception as e:
                self.logger.error(f"[CANCEL] CRITICAL: Could not get final status for order {process.last_order_id}: {e}")
                # This is a critical race condition - we have no idea what happened
                raise Exception(f"CRITICAL: Cannot determine order status for {process.last_order_id} during cancellation - race condition risk! Error: {e}")
            
        except Exception as e:
            self.logger.error(f"CRITICAL: Error cancelling order {process.last_order_id}: {e}")
            # This is a critical race condition - we couldn't even attempt cancellation
            raise Exception(f"CRITICAL: Failed to cancel order {process.last_order_id} - race condition risk! Error: {e}")

    def _wait_for_fill(self, process: WalkLimitProcess, stop_event: threading.Event, account_id: str) -> bool:
        """Wait for order to fill or timeout."""
        if not process.last_order_id:
            return False
        
        start_time = time.time()
        while time.time() - start_time < process.max_wait_time:
            if stop_event.is_set():
                return False
            
            try:
                order_status = get_order(self.client, account_id, process.last_order_id)
                if order_status.status in ['FILLED', 'PARTIALLY_FILLED']:
                    return True
                elif order_status.status in ['CANCELLED', 'REJECTED']:
                    return False
            except Exception as e:
                self.logger.error(f"Error checking order status: {e}")
            
            time.sleep(1)
        
        return False
    
    def get_all_processes(self) -> Dict[str, Dict]:
        """Get all processes with their status."""
        result = {}
        for process_id, process in self.processes.items():
            result[process_id] = {
                'symbol': process.symbol,
                'strategy': process.strategy,
                'status': process.status.value,
                'current_price': process.current_price,
                'quantity': process.quantity,
                'remaining_quantity': process.remaining_quantity,
                'attempts': process.attempts,
                'max_attempts': process.max_attempts,
                'created_at': process.created_at.isoformat(),
                'last_update': process.last_update.isoformat()
            }
        return result
    
    def cancel_process(self, process_id: str) -> bool:
        """Cancel a running process using emergency stop logic."""
        if process_id not in self.processes:
            return False
        
        process = self.processes[process_id]
        
        # Signal thread to stop
        if process_id in self.stop_events:
            self.stop_events[process_id].set()
        
        # Use emergency stop logic for consistency and safety
        account_id = config.get_default_account()
        if account_id:
            self._emergency_stop_process(process, account_id, f"Process {process_id} cancelled by user")
        else:
            # Fallback if no account ID available
            process.status = ProcessStatus.CANCELLED
            process.last_update = datetime.now()
        
        return True
    
    def emergency_cancel_all_orders(self, account_id: str):
        """
        Emergency cancellation of all active orders across all processes.
        Called during Ctrl+C or other emergency exits.
        """
        self.logger.warning("[EMERGENCY] Cancelling ALL active orders due to emergency exit")
        
        cancelled_orders = []
        failed_cancellations = []
        
        # Cancel orders from all active processes
        for process_id, process in self.processes.items():
            if process.last_order_id and process.status in [ProcessStatus.RUNNING, ProcessStatus.WAITING]:
                try:
                    self.logger.warning(f"[EMERGENCY] Cancelling order {process.last_order_id} from process {process_id}")
                    cancel_order(self.client, account_id, process.last_order_id)
                    cancelled_orders.append(process.last_order_id)
                    
                    # Mark process as stopped
                    process.status = ProcessStatus.ERROR
                    
                except Exception as e:
                    self.logger.error(f"[EMERGENCY] Failed to cancel order {process.last_order_id}: {e}")
                    failed_cancellations.append(process.last_order_id)
        
        # Stop all threads
        for process_id, stop_event in self.stop_events.items():
            stop_event.set()
        
        if cancelled_orders:
            self.logger.warning(f"[EMERGENCY] Sent cancellation requests for orders: {cancelled_orders}")
        
        if failed_cancellations:
            self.logger.error(f"[EMERGENCY] Failed to cancel orders: {failed_cancellations}")
            
        # Quick verification of cancellations (reduced timeout for emergency)
        if cancelled_orders:
            self.logger.info("[EMERGENCY] Verifying order cancellations...")
            time.sleep(2)  # Brief wait for cancellations to process
            
            for order_id in cancelled_orders:
                try:
                    order_status = get_order(self.client, account_id, order_id)
                    if order_status.status in ['CANCELLED', 'REJECTED']:
                        self.logger.info(f"[EMERGENCY] SUCCESS: Order {order_id} successfully cancelled")
                    elif order_status.status in ['FILLED', 'PARTIALLY_FILLED']:
                        self.logger.warning(f"[EMERGENCY] WARNING: Order {order_id} filled before cancellation: {order_status.status}")
                    else:
                        self.logger.warning(f"[EMERGENCY] UNCLEAR: Order {order_id} status unclear: {order_status.status}")
                except Exception as e:
                    self.logger.error(f"[EMERGENCY] Could not verify order {order_id}: {e}")
        
        return len(cancelled_orders), len(failed_cancellations)

    def wait_for_all_processes(self, timeout: Optional[int] = None) -> bool:
        """Wait for all background processes to complete.
        
        Args:
            timeout: Maximum time to wait in seconds. None for no timeout.
            
        Returns:
            True if all processes completed, False if timeout or error
        """
        import time
        start_time = time.time()
        
        while True:
            # Check if all processes are done
            active_processes = []
            for process_id, process in self.processes.items():
                if process.status in [ProcessStatus.STARTING, ProcessStatus.RUNNING, ProcessStatus.WAITING]:
                    active_processes.append(process_id)
            
            if not active_processes:
                self.logger.info("All background processes have completed")
                return True
            
            # Check timeout
            if timeout and (time.time() - start_time) > timeout:
                self.logger.warning(f"Timeout waiting for processes: {active_processes}")
                return False
            
            # Wait before checking again
            time.sleep(0.5)
    
    def has_active_processes(self) -> bool:
        """Check if there are any active background processes."""
        for process in self.processes.values():
            if process.status in [ProcessStatus.STARTING, ProcessStatus.RUNNING, ProcessStatus.WAITING]:
                return True
        return False
    
    def get_active_orders(self) -> Dict[str, str]:
        """Get all active orders that would be cancelled.
        
        Returns:
            Dict[str, str]: Mapping of process_id to order_id for active processes
        """
        active_orders = {}
        for process_id, process in self.processes.items():
            if (process.status not in [ProcessStatus.CANCELLED, ProcessStatus.COMPLETED, ProcessStatus.ERROR] 
                and process.last_order_id):
                active_orders[process_id] = process.last_order_id
        return active_orders