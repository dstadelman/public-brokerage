"""
Walk limit order engine for executing spread orders with incremental price walking.
Clean implementation based on confirmation_card.py patterns and TASKS.md requirements.
"""

import uuid
import time
import threading
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import logging

from public_brokerage.client import PublicBrokerageClient
from public_brokerage.orders import (
    preflight_multi_leg, place_multileg_order, get_order, cancel_order
)
from public_brokerage.models.order import MultiLegOrderRequest, OrderLeg, OrderType, MultiLegPreflightResponse
from public_brokerage.models.common import OrderSide, OpenCloseIndicator, InstrumentType, Instrument, Expiration, TimeInForce
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
        """Construct option symbol using same format as confirmation_card.py"""
        from datetime import datetime
        
        # Format expiration date as YYMMDD
        exp_formatted = datetime.strptime(expiration, '%Y-%m-%d').strftime('%y%m%d')
        
        # Format strike price - multiply by 100 and pad to 7 digits (like confirmation card)
        strike_formatted = f"{int(strike * 100):07d}"
        
        # Build symbol: UNDERLYING + YYMMDD + C + 7-digit-strike
        return f"{underlying}{exp_formatted}C{strike_formatted}"
    
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
            
            # Verify quotes have data
            if not (short_quote.bid and short_quote.ask and long_quote.bid and long_quote.ask):
                self.logger.error("Missing bid/ask data in quotes")
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
    
    def _run_open_spread_process(self, process: WalkLimitProcess, stop_event: threading.Event, account_id: str):
        """Run the walk limit process for opening a spread."""
        try:
            process.status = ProcessStatus.RUNNING
            
            while not stop_event.is_set() and process.attempts < process.max_attempts:
                # Check if we've reached target
                if process.current_price >= process.target_price:
                    self.logger.info(f"Process {process.process_id} reached target price")
                    break
                
                # Create and preflight order
                order_request = self._create_open_spread_order(process, account_id)
                if not order_request:
                    self.logger.error(f"Failed to create order for process {process.process_id}")
                    break
                
                # Preflight the order
                preflight_result = preflight_multi_leg(self.client, account_id, order_request)
                
                if preflight_result is None or hasattr(preflight_result, 'errorMessage'):
                    error_msg = getattr(preflight_result, 'errorMessage', 'Unknown error') if preflight_result else 'API request failed'
                    self.logger.error(f"Preflight failed for process {process.process_id}: {error_msg}")
                    break
                
                self.logger.info(f"Preflight successful for process {process.process_id} at ${process.current_price:.2f}")
                
                if process.execute_mode:
                    # Place the actual order
                    order_response = place_multileg_order(self.client, account_id, order_request)
                    if order_response.ok:
                        process.last_order_id = order_response.orderId
                        self.logger.info(f"Order placed: {order_response.orderId}")
                        
                        # Wait for fill or timeout
                        if self._wait_for_fill(process, stop_event, account_id):
                            process.status = ProcessStatus.COMPLETED
                            self.logger.info(f"Process {process.process_id} completed successfully")
                            return
                        
                        # Cancel unfilled order
                        if process.last_order_id:
                            cancel_order(self.client, account_id, process.last_order_id)
                    else:
                        self.logger.error(f"Failed to place order: {order_response.errorMessage}")
                else:
                    # Dry run - just log what would happen
                    self.logger.info(f"DRY RUN: Would place order at ${process.current_price:.2f}")
                    time.sleep(1)  # Brief pause for dry run
                
                # Move to next price level
                process.current_price = round(process.current_price + process.increment, 2)  # Round to penny
                process.attempts += 1
                process.last_update = datetime.now()
            
            process.status = ProcessStatus.COMPLETED
            
        except Exception as e:
            self.logger.error(f"Error in open spread process {process.process_id}: {e}")
            process.status = ProcessStatus.ERROR
    
    def _run_close_spread_process(self, process: WalkLimitProcess, stop_event: threading.Event, account_id: str):
        """Run the walk limit process for closing a spread."""
        try:
            process.status = ProcessStatus.RUNNING
            self.logger.info(f"[WALK] Starting close spread walk limit for {process.symbol}")
            self.logger.info(f"[PRICE] Price range: ${process.current_price:.2f} (ask) -> ${process.target_price:.2f} (bid)")
            self.logger.info(f"[INCREMENT] Increment: ${abs(process.increment):.2f}, Max attempts: {process.max_attempts}")
            
            while not stop_event.is_set() and process.attempts < process.max_attempts:
                # Check if we've reached target
                if process.current_price <= process.target_price:
                    self.logger.info(f"[TARGET] Process {process.process_id} reached target bid price ${process.target_price:.2f}")
                    break
                
                # Create and preflight order
                self.logger.info(f"[ATTEMPT] Attempt {process.attempts + 1}/{process.max_attempts}: Testing order at ${process.current_price:.2f}")
                order_request = self._create_close_spread_order(process, account_id)
                if not order_request:
                    self.logger.error(f"Failed to create order for process {process.process_id}")
                    break
                
                # Print order details - handle dict format
                if isinstance(order_request, dict):
                    limit_price = float(order_request.get('limitPrice', 0))
                    legs = order_request.get('legs', [])
                    quantity = order_request.get('quantity', 0)
                    self.logger.info(f"[ORDER] Order details: {len(legs)} legs, quantity: {quantity}, limit: ${limit_price:.2f}")
                    for i, leg in enumerate(legs):
                        side = leg.get('side', 'UNKNOWN')
                        ratio = leg.get('ratioQuantity', 0)
                        symbol = leg.get('instrument', {}).get('symbol', 'UNKNOWN')
                        close_indicator = leg.get('openCloseIndicator', 'UNKNOWN')
                        self.logger.info(f"   Leg {i+1}: {side} {ratio} {symbol} ({close_indicator})")
                else:
                    # Handle MultiLegOrderRequest object format
                    limit_price = float(order_request.limitPrice) if isinstance(order_request.limitPrice, str) else order_request.limitPrice
                    self.logger.info(f"[ORDER] Order details: {len(order_request.legs)} legs, quantity: {order_request.quantity}, limit: ${limit_price:.2f}")
                    for i, leg in enumerate(order_request.legs):
                        side_str = leg.side if isinstance(leg.side, str) else leg.side.value
                        close_str = leg.openCloseIndicator if isinstance(leg.openCloseIndicator, str) else leg.openCloseIndicator.value
                        self.logger.info(f"   Leg {i+1}: {side_str} {leg.ratioQuantity} {leg.instrument.symbol} ({close_str})")
                
                # Debug: Log the order request data
                self.logger.info(f"[DEBUG] Order request data: {order_request}")
                
                # Preflight the order - make direct API call since we have dict format
                preflight_result = self._preflight_dict_order(account_id, order_request)
                
                if preflight_result is None or hasattr(preflight_result, 'errorMessage'):
                    error_msg = getattr(preflight_result, 'errorMessage', 'Unknown error') if preflight_result else 'API request failed'
                    self.logger.error(f"[PREFLIGHT] Preflight failed for process {process.process_id}: {error_msg}")
                    break
                
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
                    # Place the actual order
                    order_response = place_multileg_order(self.client, account_id, order_request)
                    if order_response.ok:
                        process.last_order_id = order_response.orderId
                        self.logger.info(f"Order placed: {order_response.orderId}")
                        
                        # Wait for fill or timeout
                        if self._wait_for_fill(process, stop_event, account_id):
                            process.status = ProcessStatus.COMPLETED
                            self.logger.info(f"Process {process.process_id} completed successfully")
                            return
                        
                        # Cancel unfilled order
                        if process.last_order_id:
                            cancel_order(self.client, account_id, process.last_order_id)
                    else:
                        self.logger.error(f"Failed to place order: {order_response.errorMessage}")
                else:
                    # Dry run - just log what would happen
                    self.logger.info(f"DRY RUN: Would place order at ${process.current_price:.2f}")
                    time.sleep(1)  # Brief pause for dry run
                
                # Move to next price level (walking down for closing)
                next_price = round(process.current_price + process.increment, 2)  # increment is negative for closing, round to penny
                self.logger.info(f"[WALK] Walking price down from ${process.current_price:.2f} to ${next_price:.2f}")
                process.current_price = next_price
                process.attempts += 1
                process.last_update = datetime.now()
            
            process.status = ProcessStatus.COMPLETED
            
        except Exception as e:
            self.logger.error(f"Error in close spread process {process.process_id}: {e}")
            process.status = ProcessStatus.ERROR
    
    def _create_open_spread_order(self, process: WalkLimitProcess, account_id: str) -> Optional[MultiLegOrderRequest]:
        """Create multi-leg order for opening a spread using rPublic.R pattern."""
        try:
            # Create legs following the rPublic.R pattern
            legs = []
            
            # Short leg (sell call)
            short_leg = OrderLeg(
                instrument=Instrument(symbol=process.short_symbol, type=InstrumentType.OPTION),
                side=OrderSide.SELL,
                openCloseIndicator=OpenCloseIndicator.OPEN,
                ratioQuantity=process.quantity
            )
            legs.append(short_leg)
            
            # Long leg (buy call)
            long_leg = OrderLeg(
                instrument=Instrument(symbol=process.long_symbol, type=InstrumentType.OPTION),
                side=OrderSide.BUY,
                openCloseIndicator=OpenCloseIndicator.OPEN,
                ratioQuantity=process.quantity
            )
            legs.append(long_leg)
            
            # Create multi-leg order with proper expiration and required fields
            expiration = Expiration(timeInForce=TimeInForce.DAY)
            return MultiLegOrderRequest(
                orderId=None,  # Don't include orderId for preflight
                quantity=process.quantity,
                type=OrderType.LIMIT,
                limitPrice=str(process.current_price),
                expiration=expiration,
                legs=legs
            )
            
        except Exception as e:
            self.logger.error(f"Error creating open spread order: {e}")
            return None
    
    def _create_close_spread_order(self, process: WalkLimitProcess, account_id: str) -> Optional[dict]:
        """Create multi-leg order for closing a spread using correct API format."""
        try:
            # Create legs following the API documentation format
            legs = []
            
            # Short leg (buy to close) - ratio is 1 per spread
            short_leg = {
                "instrument": {
                    "symbol": process.short_symbol,
                    "type": "OPTION"
                },
                "side": "BUY",
                "openCloseIndicator": "CLOSE",
                "ratioQuantity": 1  # 1 contract per spread
            }
            legs.append(short_leg)
            
            # Long leg (sell to close) - ratio is 1 per spread
            long_leg = {
                "instrument": {
                    "symbol": process.long_symbol,
                    "type": "OPTION"
                },
                "side": "SELL",
                "openCloseIndicator": "CLOSE",
                "ratioQuantity": 1  # 1 contract per spread
            }
            legs.append(long_leg)
            
            # Create order request in correct API format
            return {
                "orderType": "LIMIT",  # Note: orderType not type
                "expiration": {
                    "timeInForce": "DAY",
                    "expirationTime": None  # DAY orders don't need specific time
                },
                "quantity": str(process.quantity),
                "limitPrice": str(-process.current_price),  # Send NEGATIVE for closing (we want credit)
                "legs": legs
            }
            
        except Exception as e:
            self.logger.error(f"Error creating close spread order: {e}")
            return None
    
    def _preflight_dict_order(self, account_id: str, order_dict: dict):
        """Preflight order using dict format directly."""
        try:
            # Ensure we have a valid access token
            ensure_access_token(self.client)
            
            # Make the API request
            response = self.client._make_request(
                method="POST",
                endpoint=f"/userapigateway/trading/{account_id}/preflight/multi-leg",
                data=order_dict
            )
            
            # Parse response
            return self.client._handle_response(response, MultiLegPreflightResponse)
            
        except Exception as e:
            self.logger.error(f"Preflight request failed: {e}")
            # Return a mock response for error handling
            class MockResponse:
                def __init__(self):
                    self.ok = False
                    self.errorMessage = str(e)
            return MockResponse()
    
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
                'attempts': process.attempts,
                'max_attempts': process.max_attempts,
                'created_at': process.created_at.isoformat(),
                'last_update': process.last_update.isoformat()
            }
        return result
    
    def cancel_process(self, process_id: str) -> bool:
        """Cancel a running process."""
        if process_id not in self.processes:
            return False
        
        # Signal thread to stop
        if process_id in self.stop_events:
            self.stop_events[process_id].set()
        
        # Cancel any pending order
        process = self.processes[process_id]
        if process.last_order_id and process.execute_mode:
            try:
                account_id = config.get_default_account()
                if account_id:
                    cancel_order(self.client, account_id, process.last_order_id)
            except Exception as e:
                self.logger.error(f"Error cancelling order: {e}")
        
        process.status = ProcessStatus.CANCELLED
        process.last_update = datetime.now()
        
        return True
    
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