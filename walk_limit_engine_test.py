"""
Comprehensive unit tests for the Walk Limit Engine.

Tests all functionality including:
- Order placement and preflight
- Partial fill handling
- Cancel verification
- Quantity tracking
- Error conditions
- Both opening and closing spreads
"""

import unittest
from unittest.mock import Mock, MagicMock, patch, call
import threading
import time
import logging
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

from walk_limit_engine import WalkLimitEngine, WalkLimitProcess, ProcessStatus
from public_brokerage.client import PublicBrokerageClient
from public_brokerage.models.order import MultiLegPreflightResponse, RegulatoryFees, PriceIncrement
from public_brokerage.models.common import Instrument, InstrumentType


class MockOrderStatus:
    """Mock order status response."""
    def __init__(self, status: str, filled_quantity: str = "0"):
        self.status = status
        self.filledQuantity = filled_quantity


class MockOrderResponse:
    """Mock order placement response."""
    def __init__(self, ok: bool = True, order_id: str = "TEST123", error_message: str = ""):
        self.ok = ok
        self.orderId = order_id
        self.errorMessage = error_message


class MockQuoteResponse:
    """Mock quote response."""
    def __init__(self, bid: str = "1.50", ask: str = "1.60", outcome: str = "SUCCESS"):
        self.bid = bid
        self.ask = ask
        self.outcome = outcome


class MockPreflightResponse:
    """Mock preflight response."""
    def __init__(self, success: bool = True):
        if success:
            self.baseSymbol = "ORCL"
            self.strategyName = "ORCL Long Call Calendar Spread"
            self.estimatedCost = "-432.05"
            self.estimatedProceeds = "432.05"
            self.orderValue = "-432.00"
            self.estimatedCommission = "0.24"
            self.buyingPowerRequirement = "-431.81"
            self.regulatoryFees = RegulatoryFees(
                secFee="0.00",
                tafFee="0.01", 
                orfFee="0.10",
                exchangeFee=None,
                occFee="0.08",
                catFee="0.00"
            )
            self.priceIncrement = PriceIncrement(
                incrementBelow3="0.01",
                incrementAbove3="0.05",
                currentIncrement="0.01"
            )
        else:
            self.errorMessage = "Preflight failed"


class WalkLimitEngineTest(unittest.TestCase):
    """Test cases for WalkLimitEngine."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=PublicBrokerageClient)
        self.engine = WalkLimitEngine(self.mock_client)
        self.account_id = "TEST_ACCOUNT"
        
        # Mock spread data
        self.mock_spread = Mock()
        self.mock_spread.short_symbol = "ORCL250912C00240000"
        self.mock_spread.long_symbol = "ORCL251017C00240000"
        self.mock_spread.quantity = 2
        
    def tearDown(self):
        """Clean up after tests."""
        # Cancel any active processes
        self.engine.cancel_all_processes()
        time.sleep(0.1)  # Allow threads to finish
    
    @patch('walk_limit_engine.get_quotes')
    @patch('walk_limit_engine.ensure_access_token')
    def test_get_spread_pricing_success(self, mock_ensure_token, mock_get_quotes):
        """Test successful spread pricing calculation."""
        # Mock quote responses
        short_quote = MockQuoteResponse(bid="90.80", ask="91.25")
        long_quote = MockQuoteResponse(bid="91.70", ask="93.05")
        mock_get_quotes.return_value = [short_quote, long_quote]
        
        bid, ask = self.engine._get_spread_pricing("ORCL250912C00240000", "ORCL251017C00240000", self.account_id)
        
        # For closing: bid = long_bid - short_ask, ask = long_ask - short_bid
        expected_bid = 91.70 - 91.25  # 0.45
        expected_ask = 93.05 - 90.80  # 2.25
        
        self.assertAlmostEqual(bid, expected_bid, places=2)
        self.assertAlmostEqual(ask, expected_ask, places=2)
        
        # Verify API calls
        mock_ensure_token.assert_called_once()
        self.assertEqual(mock_get_quotes.call_count, 2)
    
    @patch('walk_limit_engine.get_quotes')
    def test_get_spread_pricing_failure(self, mock_get_quotes):
        """Test spread pricing with API failure."""
        mock_get_quotes.side_effect = Exception("API Error")
        
        bid, ask = self.engine._get_spread_pricing("ORCL250912C00240000", "ORCL251017C00240000", self.account_id)
        
        self.assertIsNone(bid)
        self.assertIsNone(ask)
    
    def test_process_creation_with_remaining_quantity(self):
        """Test that processes are created with correct remaining quantity."""
        with patch.object(self.engine, '_get_spread_pricing', return_value=(0.45, 2.25)):
            process_id = self.engine.start_open_call_spread_process(
                symbol="ORCL",
                short_expiration="2025-09-12", 
                short_strike=240.0,
                long_expiration="2025-10-17",
                long_strike=240.0,
                quantity=5,
                account_id=self.account_id,
                max_wait_time=30,
                execute_mode=False
            )
        
        self.assertIsNotNone(process_id)
        process = self.engine.processes[process_id]
        
        # Verify initial quantities
        self.assertEqual(process.quantity, 5)
        self.assertEqual(process.remaining_quantity, 5)
        self.assertEqual(process.status, ProcessStatus.STARTING)
    
    @patch('walk_limit_engine.get_order')
    def test_wait_for_fill_with_complete_fill(self, mock_get_order):
        """Test waiting for complete fill."""
        # Create a test process
        process = WalkLimitProcess(
            process_id="test123",
            symbol="ORCL",
            strategy="close_call_spread",
            short_symbol="ORCL250912C00240000",
            long_symbol="ORCL251017C00240000", 
            quantity=2,
            remaining_quantity=2,
            max_wait_time=5,
            execute_mode=True,
            status=ProcessStatus.RUNNING,
            current_price=1.50,
            target_price=0.45,
            increment=-0.09,
            attempts=0,
            max_attempts=20,
            created_at=datetime.now(),
            last_update=datetime.now(),
            last_order_id="ORDER123"
        )
        
        # Mock complete fill
        mock_get_order.return_value = MockOrderStatus("FILLED", "2")
        
        stop_event = threading.Event()
        is_complete, filled_qty = self.engine._wait_for_fill_with_partial_handling(
            process, stop_event, self.account_id
        )
        
        self.assertTrue(is_complete)
        self.assertEqual(filled_qty, 2)
        mock_get_order.assert_called_with(self.mock_client, self.account_id, "ORDER123")
    
    @patch('walk_limit_engine.get_order')
    def test_wait_for_fill_with_partial_fill(self, mock_get_order):
        """Test waiting for partial fill."""
        process = WalkLimitProcess(
            process_id="test123",
            symbol="ORCL", 
            strategy="close_call_spread",
            short_symbol="ORCL250912C00240000",
            long_symbol="ORCL251017C00240000",
            quantity=5,
            remaining_quantity=5,
            max_wait_time=5,
            execute_mode=True,
            status=ProcessStatus.RUNNING,
            current_price=1.50,
            target_price=0.45,
            increment=-0.09,
            attempts=0,
            max_attempts=20,
            created_at=datetime.now(),
            last_update=datetime.now(),
            last_order_id="ORDER123"
        )
        
        # Mock partial fill
        mock_get_order.return_value = MockOrderStatus("PARTIALLY_FILLED", "3")
        
        stop_event = threading.Event()
        is_complete, filled_qty = self.engine._wait_for_fill_with_partial_handling(
            process, stop_event, self.account_id
        )
        
        self.assertFalse(is_complete)  # Not complete - still have unfilled quantity
        self.assertEqual(filled_qty, 3)
    
    @patch('walk_limit_engine.get_order')
    def test_wait_for_fill_timeout_with_partial(self, mock_get_order):
        """Test timeout with partial fill."""
        process = WalkLimitProcess(
            process_id="test123",
            symbol="ORCL",
            strategy="close_call_spread", 
            short_symbol="ORCL250912C00240000",
            long_symbol="ORCL251017C00240000",
            quantity=5,
            remaining_quantity=5,
            max_wait_time=1,  # Short timeout
            execute_mode=True,
            status=ProcessStatus.RUNNING,
            current_price=1.50,
            target_price=0.45,
            increment=-0.09,
            attempts=0,
            max_attempts=20,
            created_at=datetime.now(),
            last_update=datetime.now(),
            last_order_id="ORDER123"
        )
        
        # Mock order status that stays working then shows partial fill
        mock_get_order.side_effect = [
            MockOrderStatus("WORKING", "0"),  # First check
            MockOrderStatus("WORKING", "0"),  # Second check  
            MockOrderStatus("PARTIALLY_FILLED", "2")  # Final check after timeout
        ]
        
        stop_event = threading.Event()
        is_complete, filled_qty = self.engine._wait_for_fill_with_partial_handling(
            process, stop_event, self.account_id
        )
        
        self.assertFalse(is_complete)
        self.assertEqual(filled_qty, 2)
        self.assertEqual(mock_get_order.call_count, 3)  # Initial checks + final check
    
    @patch('walk_limit_engine.get_order')
    @patch('walk_limit_engine.cancel_order')
    def test_cancel_order_with_verification_success(self, mock_cancel, mock_get_order):
        """Test successful order cancellation with verification."""
        process = WalkLimitProcess(
            process_id="test123",
            symbol="ORCL",
            strategy="close_call_spread",
            short_symbol="ORCL250912C00240000", 
            long_symbol="ORCL251017C00240000",
            quantity=2,
            remaining_quantity=2,
            max_wait_time=30,
            execute_mode=True,
            status=ProcessStatus.RUNNING,
            current_price=1.50,
            target_price=0.45,
            increment=-0.09,
            attempts=0,
            max_attempts=20,
            created_at=datetime.now(),
            last_update=datetime.now(),
            last_order_id="ORDER123"
        )
        
        # Mock successful cancellation
        mock_get_order.return_value = MockOrderStatus("CANCELLED", "0")
        
        success = self.engine._cancel_order_with_verification(process, self.account_id)
        
        self.assertTrue(success)
        mock_cancel.assert_called_once_with(self.mock_client, self.account_id, "ORDER123")
        mock_get_order.assert_called_with(self.mock_client, self.account_id, "ORDER123")
    
    @patch('walk_limit_engine.get_order')
    @patch('walk_limit_engine.cancel_order')
    def test_cancel_order_filled_during_cancel(self, mock_cancel, mock_get_order):
        """Test order getting filled while trying to cancel."""
        process = WalkLimitProcess(
            process_id="test123",
            symbol="ORCL",
            strategy="close_call_spread",
            short_symbol="ORCL250912C00240000",
            long_symbol="ORCL251017C00240000", 
            quantity=2,
            remaining_quantity=2,
            max_wait_time=30,
            execute_mode=True,
            status=ProcessStatus.RUNNING,
            current_price=1.50,
            target_price=0.45,
            increment=-0.09,
            attempts=0,
            max_attempts=20,
            created_at=datetime.now(),
            last_update=datetime.now(),
            last_order_id="ORDER123"
        )
        
        # Mock order getting filled during cancel attempt
        mock_get_order.return_value = MockOrderStatus("FILLED", "2")
        
        success = self.engine._cancel_order_with_verification(process, self.account_id)
        
        self.assertFalse(success)  # Cancel "failed" because order filled
        mock_cancel.assert_called_once()
    
    @patch('walk_limit_engine.get_order')  
    @patch('walk_limit_engine.cancel_order')
    def test_cancel_order_verification_timeout(self, mock_cancel, mock_get_order):
        """Test cancel verification timeout."""
        process = WalkLimitProcess(
            process_id="test123",
            symbol="ORCL",
            strategy="close_call_spread",
            short_symbol="ORCL250912C00240000",
            long_symbol="ORCL251017C00240000",
            quantity=2,
            remaining_quantity=2,
            max_wait_time=30,
            execute_mode=True,
            status=ProcessStatus.RUNNING,
            current_price=1.50,
            target_price=0.45,
            increment=-0.09,
            attempts=0,
            max_attempts=20,
            created_at=datetime.now(),
            last_update=datetime.now(),
            last_order_id="ORDER123"
        )
        
        # Mock order that never gets cancelled (stays WORKING)
        mock_get_order.return_value = MockOrderStatus("WORKING", "0")
        
        with patch('time.sleep'):  # Speed up the test
            success = self.engine._cancel_order_with_verification(process, self.account_id)
        
        self.assertFalse(success)
        mock_cancel.assert_called_once()
        self.assertEqual(mock_get_order.call_count, 10)  # Max cancel checks
    
    @patch('walk_limit_engine.place_multileg_order')
    @patch('walk_limit_engine.get_order')
    @patch('walk_limit_engine.cancel_order')
    def test_full_process_with_partial_fills(self, mock_cancel, mock_get_order, mock_place_order):
        """Test complete process with partial fills and quantity tracking."""
        # Mock successful order placement
        mock_place_order.return_value = MockOrderResponse(True, "ORDER123")
        
        # Mock a sequence: partial fill, then complete fill on second attempt
        mock_get_order.side_effect = [
            # First attempt - partial fill after timeout 
            MockOrderStatus("WORKING", "0"),
            MockOrderStatus("PARTIALLY_FILLED", "1"),  # Final check shows 1 filled
            MockOrderStatus("CANCELLED", "1"),  # Cancel verification
            # Second attempt - complete fill
            MockOrderStatus("FILLED", "1")  # Remaining 1 gets filled
        ]
        
        # Create a process manually for testing
        process = WalkLimitProcess(
            process_id="test123",
            symbol="ORCL",
            strategy="close_call_spread",
            short_symbol="ORCL250912C00240000",
            long_symbol="ORCL251017C00240000",
            quantity=2,
            remaining_quantity=2,
            max_wait_time=1,  # Short timeout to speed up test
            execute_mode=True,
            status=ProcessStatus.STARTING,
            current_price=1.50,
            target_price=0.45,
            increment=-0.09,
            attempts=0,
            max_attempts=20,
            created_at=datetime.now(),
            last_update=datetime.now()
        )
        
        # Mock preflight success
        with patch.object(self.engine, '_create_close_spread_order', return_value={"test": "order"}):
            with patch.object(self.engine, '_preflight_dict_order', return_value=MockPreflightResponse(True)):
                with patch('time.sleep'):  # Speed up sleeps
                    stop_event = threading.Event()
                    
                    # Add process to engine 
                    self.engine.processes["test123"] = process
                    
                    # Run the process
                    self.engine._run_close_spread_process(process, stop_event, self.account_id)
        
        # Verify final state
        self.assertEqual(process.status, ProcessStatus.COMPLETED)
        self.assertEqual(process.remaining_quantity, 0)  # All quantity filled
        
        # Verify call sequence
        self.assertEqual(mock_place_order.call_count, 2)  # Two order attempts
        mock_cancel.assert_called_once()  # One cancel after partial fill
    
    def test_dry_run_mode(self):
        """Test dry run mode doesn't place actual orders."""
        with patch.object(self.engine, '_get_spread_pricing', return_value=(0.45, 2.25)):
            with patch.object(self.engine, '_create_close_spread_order', return_value={"test": "order"}):
                with patch.object(self.engine, '_preflight_dict_order', return_value=MockPreflightResponse(True)):
                    with patch('time.sleep'):  # Speed up dry run sleeps
                        
                        process_id = self.engine.start_close_call_spread_process(
                            symbol="ORCL",
                            spreads=[self.mock_spread],
                            account_id=self.account_id,
                            max_wait_time=30,
                            execute_mode=False  # DRY RUN
                        )[0]
                        
                        # Wait for process to complete
                        time.sleep(0.5)
                        
                        process = self.engine.processes[process_id]
                        
                        # In dry run, should complete without actual orders
                        self.assertEqual(process.status, ProcessStatus.COMPLETED)
                        self.assertIsNone(process.last_order_id)
    
    def test_quantity_tracking_in_status(self):
        """Test that process status includes quantity information."""
        with patch.object(self.engine, '_get_spread_pricing', return_value=(0.45, 2.25)):
            process_id = self.engine.start_open_call_spread_process(
                symbol="ORCL",
                short_expiration="2025-09-12",
                short_strike=240.0,
                long_expiration="2025-10-17", 
                long_strike=240.0,
                quantity=5,
                account_id=self.account_id,
                max_wait_time=30,
                execute_mode=False
            )
        
        status = self.engine.get_all_processes()
        process_info = status[process_id]
        
        self.assertEqual(process_info['quantity'], 5)
        self.assertEqual(process_info['remaining_quantity'], 5)
        self.assertIn('symbol', process_info)
        self.assertIn('strategy', process_info)
    
    def test_safety_check_zero_remaining_quantity(self):
        """Test safety check prevents orders with zero remaining quantity."""
        # Create process with zero remaining quantity
        process = WalkLimitProcess(
            process_id="test123",
            symbol="ORCL",
            strategy="close_call_spread",
            short_symbol="ORCL250912C00240000",
            long_symbol="ORCL251017C00240000",
            quantity=2,
            remaining_quantity=0,  # No remaining quantity
            max_wait_time=30,
            execute_mode=True,
            status=ProcessStatus.RUNNING,
            current_price=1.50,
            target_price=0.45,
            increment=-0.09,
            attempts=0,
            max_attempts=20,
            created_at=datetime.now(),
            last_update=datetime.now()
        )
        
        stop_event = threading.Event()
        self.engine._run_close_spread_process(process, stop_event, self.account_id)
        
        # Should complete immediately due to safety check
        self.assertEqual(process.status, ProcessStatus.COMPLETED)
        self.assertEqual(process.attempts, 0)  # No attempts made
    
    def test_error_handling_preflight_failure(self):
        """Test error handling when preflight fails."""
        with patch.object(self.engine, '_get_spread_pricing', return_value=(0.45, 2.25)):
            with patch.object(self.engine, '_create_close_spread_order', return_value={"test": "order"}):
                with patch.object(self.engine, '_preflight_dict_order', return_value=MockPreflightResponse(False)):
                    
                    process_id = self.engine.start_close_call_spread_process(
                        symbol="ORCL",
                        spreads=[self.mock_spread],
                        account_id=self.account_id,
                        max_wait_time=30,
                        execute_mode=False
                    )[0]
                    
                    # Wait for process to complete
                    time.sleep(0.5)
                    
                    process = self.engine.processes[process_id]
                    
                    # Should complete due to preflight failure
                    self.assertEqual(process.status, ProcessStatus.COMPLETED)
    
    def test_process_cancellation(self):
        """Test process cancellation functionality."""
        with patch.object(self.engine, '_get_spread_pricing', return_value=(0.45, 2.25)):
            process_id = self.engine.start_open_call_spread_process(
                symbol="ORCL",
                short_expiration="2025-09-12",
                short_strike=240.0,
                long_expiration="2025-10-17",
                long_strike=240.0,
                quantity=2,
                account_id=self.account_id,
                max_wait_time=30,
                execute_mode=False
            )
        
        # Cancel the process
        success = self.engine.cancel_process(process_id)
        self.assertTrue(success)
        
        # Verify stop event was set
        self.assertTrue(self.engine.stop_events[process_id].is_set())
    
    def test_cancel_all_processes(self):
        """Test cancelling all processes."""
        with patch.object(self.engine, '_get_spread_pricing', return_value=(0.45, 2.25)):
            # Start multiple processes
            process_id1 = self.engine.start_open_call_spread_process(
                symbol="ORCL",
                short_expiration="2025-09-12",
                short_strike=240.0,
                long_expiration="2025-10-17", 
                long_strike=240.0,
                quantity=2,
                account_id=self.account_id,
                max_wait_time=30,
                execute_mode=False
            )
            
            process_id2 = self.engine.start_close_call_spread_process(
                symbol="ORCL",
                spreads=[self.mock_spread],
                account_id=self.account_id,
                max_wait_time=30,
                execute_mode=False
            )[0]
        
        # Cancel all processes
        count = self.engine.cancel_all_processes()
        self.assertEqual(count, 2)
        
        # Verify all stop events were set
        for stop_event in self.engine.stop_events.values():
            self.assertTrue(stop_event.is_set())


if __name__ == '__main__':
    # Configure logging for tests
    logging.basicConfig(level=logging.DEBUG)
    
    # Run the tests
    unittest.main(verbosity=2)
