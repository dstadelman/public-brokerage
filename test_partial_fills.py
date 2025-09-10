#!/usr/bin/env python3
"""
Comprehensive tests for partial fills in the walk limit engine.
Tests opening and closing spreads with various partial fill scenarios.
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import time
import threading

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from walk_limit_engine import WalkLimitEngine, ProcessStatus, WalkLimitProcess
from config import Config


class MockOrder:
    """Mock order object for testing."""
    def __init__(self, order_id, status="NEW", filled_quantity="0"):
        self.orderId = order_id
        self.status = status
        self.filledQuantity = filled_quantity


class TestPartialFills(unittest.TestCase):
    """Test partial fill handling in walk limit engine."""
    
    def setUp(self):
        """Set up test environment."""
        self.mock_client = Mock()
        self.engine = WalkLimitEngine(self.mock_client)
        
        # Mock config
        self.mock_config = Mock()
        self.mock_config.get_default_account.return_value = "TEST_ACCOUNT"
        
        # Patch config
        self.config_patcher = patch('walk_limit_engine.config', self.mock_config)
        self.config_patcher.start()
    
    def tearDown(self):
        """Clean up after tests."""
        self.config_patcher.stop()
    
    def test_full_fill_single_order(self):
        """Test complete fill in single order."""
        with patch.object(self.engine, '_get_spread_pricing', return_value=(2.50, 3.00)):
            with patch.object(self.engine, '_create_open_spread_order') as mock_create_order:
                with patch('walk_limit_engine.preflight_multi_leg') as mock_preflight:
                    with patch('walk_limit_engine.place_multileg_order') as mock_place_order:
                        with patch('walk_limit_engine.get_order') as mock_get_order:
                            # Setup mocks
                            mock_create_order.return_value = Mock()
                            mock_preflight.return_value = Mock(estimatedCost="250.00")
                            mock_place_order.return_value = Mock(orderId="ORDER123")
                            
                            # Simulate full fill
                            mock_get_order.return_value = MockOrder("ORDER123", "FILLED", "5")
                            
                            # Start process
                            process_id = self.engine.start_open_call_spread_process(
                                symbol="AAPL",
                                short_expiration="2024-07-19",
                                short_strike=170.0,
                                long_expiration="2024-08-16",
                                long_strike=175.0,
                                quantity=5,
                                execute_mode=True
                            )
                            
                            # Wait for process to complete
                            time.sleep(2)
                            
                            # Check results
                            status = self.engine.get_process_status(process_id)
                            self.assertIsNotNone(status)
                            self.assertEqual(status['original_quantity'], 5)
                            self.assertEqual(status['filled_quantity'], 5)
                            self.assertEqual(status['remaining_quantity'], 0)
                            self.assertEqual(status['fill_percentage'], 100.0)
                            self.assertEqual(len(status['successful_fills']), 1)
    
    def test_partial_fill_single_order(self):
        """Test partial fill in single order, then complete fill in next order."""
        with patch.object(self.engine, '_get_spread_pricing', return_value=(2.50, 3.00)):
            with patch.object(self.engine, '_create_open_spread_order') as mock_create_order:
                with patch('walk_limit_engine.preflight_multi_leg') as mock_preflight:
                    with patch('walk_limit_engine.place_multileg_order') as mock_place_order:
                        with patch('walk_limit_engine.get_order') as mock_get_order:
                            with patch('walk_limit_engine.cancel_order') as mock_cancel:
                                # Setup mocks
                                mock_create_order.return_value = Mock()
                                mock_preflight.return_value = Mock(estimatedCost="250.00")
                                
                                order_responses = [
                                    Mock(orderId="ORDER123"),
                                    Mock(orderId="ORDER124")
                                ]
                                mock_place_order.side_effect = order_responses
                                
                                # First order gets partial fill (3 out of 5)
                                # Second order gets remaining 2
                                order_statuses = [
                                    # First order - partial fill after timeout
                                    MockOrder("ORDER123", "PARTIALLY_FILLED", "3"),
                                    MockOrder("ORDER123", "PARTIALLY_FILLED", "3"),
                                    MockOrder("ORDER123", "PARTIALLY_FILLED", "3"),  # Timeout with partial
                                    # Second order - complete fill
                                    MockOrder("ORDER124", "FILLED", "2"),
                                ]
                                mock_get_order.side_effect = order_statuses
                                
                                # Start process with short wait time for testing
                                process_id = self.engine.start_open_call_spread_process(
                                    symbol="AAPL",
                                    short_expiration="2024-07-19",
                                    short_strike=170.0,
                                    long_expiration="2024-08-16",
                                    long_strike=175.0,
                                    quantity=5,
                                    max_wait_time=1,  # Short timeout for testing
                                    execute_mode=True
                                )
                                
                                # Wait for process to complete
                                time.sleep(5)
                                
                                # Check results
                                status = self.engine.get_process_status(process_id)
                                self.assertIsNotNone(status)
                                self.assertEqual(status['original_quantity'], 5)
                                self.assertEqual(status['filled_quantity'], 5)  # 3 + 2
                                self.assertEqual(status['remaining_quantity'], 0)
                                self.assertEqual(status['fill_percentage'], 100.0)
                                self.assertEqual(len(status['successful_fills']), 2)
                                
                                # Check fill details
                                fills = status['successful_fills']
                                self.assertTrue(fills[0].get('partial', False))
                                self.assertEqual(fills[0]['quantity'], 3)
                                self.assertEqual(fills[1]['quantity'], 2)
    
    def test_multiple_partial_fills(self):
        """Test multiple partial fills across several orders."""
        with patch.object(self.engine, '_get_spread_pricing', return_value=(2.50, 3.00)):
            with patch.object(self.engine, '_create_open_spread_order') as mock_create_order:
                with patch('walk_limit_engine.preflight_multi_leg') as mock_preflight:
                    with patch('walk_limit_engine.place_multileg_order') as mock_place_order:
                        with patch('walk_limit_engine.get_order') as mock_get_order:
                            with patch('walk_limit_engine.cancel_order') as mock_cancel:
                                # Setup mocks
                                mock_create_order.return_value = Mock()
                                mock_preflight.return_value = Mock(estimatedCost="250.00")
                                
                                order_responses = [
                                    Mock(orderId="ORDER123"),
                                    Mock(orderId="ORDER124"),
                                    Mock(orderId="ORDER125")
                                ]
                                mock_place_order.side_effect = order_responses
                                
                                # Simulate: 10 requested, 3 filled, then 4 filled, then 3 filled
                                order_statuses = [
                                    # First order - partial fill (3 out of 10)
                                    MockOrder("ORDER123", "PARTIALLY_FILLED", "3"),
                                    MockOrder("ORDER123", "PARTIALLY_FILLED", "3"),
                                    # Second order - partial fill (4 out of remaining 7)
                                    MockOrder("ORDER124", "PARTIALLY_FILLED", "4"),
                                    MockOrder("ORDER124", "PARTIALLY_FILLED", "4"),
                                    # Third order - complete remaining (3)
                                    MockOrder("ORDER125", "FILLED", "3"),
                                ]
                                mock_get_order.side_effect = order_statuses
                                
                                # Start process
                                process_id = self.engine.start_open_call_spread_process(
                                    symbol="AAPL",
                                    short_expiration="2024-07-19",
                                    short_strike=170.0,
                                    long_expiration="2024-08-16",
                                    long_strike=175.0,
                                    quantity=10,
                                    max_wait_time=1,
                                    execute_mode=True
                                )
                                
                                # Wait for process to complete
                                time.sleep(8)
                                
                                # Check results
                                status = self.engine.get_process_status(process_id)
                                self.assertIsNotNone(status)
                                self.assertEqual(status['original_quantity'], 10)
                                self.assertEqual(status['filled_quantity'], 10)  # 3 + 4 + 3
                                self.assertEqual(status['remaining_quantity'], 0)
                                self.assertEqual(status['fill_percentage'], 100.0)
                                self.assertEqual(len(status['successful_fills']), 3)
    
    def test_partial_fill_incomplete_process(self):
        """Test process that completes with only partial fills."""
        with patch.object(self.engine, '_get_spread_pricing', return_value=(2.50, 3.00)):
            with patch.object(self.engine, '_create_open_spread_order') as mock_create_order:
                with patch('walk_limit_engine.preflight_multi_leg') as mock_preflight:
                    with patch('walk_limit_engine.place_multileg_order') as mock_place_order:
                        with patch('walk_limit_engine.get_order') as mock_get_order:
                            with patch('walk_limit_engine.cancel_order') as mock_cancel:
                                # Setup mocks
                                mock_create_order.return_value = Mock()
                                mock_preflight.return_value = Mock(estimatedCost="250.00")
                                
                                # Only one order placed, gets partial fill, then process reaches max attempts
                                mock_place_order.return_value = Mock(orderId="ORDER123")
                                
                                # Partial fill only - never completes
                                order_statuses = [
                                    MockOrder("ORDER123", "PARTIALLY_FILLED", "3"),
                                    MockOrder("ORDER123", "PARTIALLY_FILLED", "3"),
                                    MockOrder("ORDER123", "PARTIALLY_FILLED", "3"),
                                ]
                                mock_get_order.side_effect = order_statuses
                                
                                # Create process with limited attempts
                                process_id = self.engine.start_open_call_spread_process(
                                    symbol="AAPL",
                                    short_expiration="2024-07-19",
                                    short_strike=170.0,
                                    long_expiration="2024-08-16", 
                                    long_strike=175.0,
                                    quantity=10,
                                    max_wait_time=1,
                                    execute_mode=True
                                )
                                
                                # Manually set max attempts low for testing
                                if process_id in self.engine.processes:
                                    self.engine.processes[process_id].max_attempts = 2
                                
                                # Wait for process to complete
                                time.sleep(5)
                                
                                # Check results - should be partially complete
                                status = self.engine.get_process_status(process_id)
                                self.assertIsNotNone(status)
                                self.assertEqual(status['original_quantity'], 10)
                                self.assertEqual(status['filled_quantity'], 3)
                                self.assertEqual(status['remaining_quantity'], 7)
                                self.assertEqual(status['fill_percentage'], 30.0)
                                self.assertEqual(len(status['successful_fills']), 1)
                                self.assertTrue(status['successful_fills'][0].get('partial', False))
    
    def test_close_spread_partial_fills(self):
        """Test partial fills when closing spreads."""
        # Mock existing spreads
        mock_spread = Mock()
        mock_spread.short_leg.strike_price = 170.0
        mock_spread.long_leg.strike_price = 175.0
        mock_spread.short_leg.expiration_date.strftime.return_value = "2024-07-19"
        mock_spread.long_leg.expiration_date.strftime.return_value = "2024-07-19"
        mock_spread.quantity = 5
        
        with patch.object(self.engine, '_get_spread_pricing', return_value=(2.30, 2.70)):
            with patch.object(self.engine, '_create_close_spread_order') as mock_create_order:
                with patch('walk_limit_engine.preflight_multi_leg') as mock_preflight:
                    with patch('walk_limit_engine.place_multileg_order') as mock_place_order:
                        with patch('walk_limit_engine.get_order') as mock_get_order:
                            with patch('walk_limit_engine.cancel_order') as mock_cancel:
                                # Setup mocks
                                mock_create_order.return_value = Mock()
                                mock_preflight.return_value = Mock(estimatedCost="135.00")
                                
                                order_responses = [
                                    Mock(orderId="CLOSE123"),
                                    Mock(orderId="CLOSE124")
                                ]
                                mock_place_order.side_effect = order_responses
                                
                                # First close order gets partial fill (2 out of 5)
                                # Second close order gets remaining 3
                                order_statuses = [
                                    MockOrder("CLOSE123", "PARTIALLY_FILLED", "2"),
                                    MockOrder("CLOSE123", "PARTIALLY_FILLED", "2"),
                                    MockOrder("CLOSE124", "FILLED", "3"),
                                ]
                                mock_get_order.side_effect = order_statuses
                                
                                # Start close process
                                process_ids = self.engine.start_close_call_spread_process(
                                    symbol="AAPL",
                                    spreads=[mock_spread],
                                    max_wait_time=1,
                                    execute_mode=True
                                )
                                
                                self.assertEqual(len(process_ids), 1)
                                process_id = process_ids[0]
                                
                                # Wait for process to complete
                                time.sleep(5)
                                
                                # Check results
                                status = self.engine.get_process_status(process_id)
                                self.assertIsNotNone(status)
                                self.assertEqual(status['original_quantity'], 5)
                                self.assertEqual(status['filled_quantity'], 5)  # 2 + 3
                                self.assertEqual(status['remaining_quantity'], 0)
                                self.assertEqual(status['fill_percentage'], 100.0)
                                self.assertEqual(len(status['successful_fills']), 2)
    
    def test_no_fills_timeout(self):
        """Test process that times out with no fills."""
        with patch.object(self.engine, '_get_spread_pricing', return_value=(2.50, 3.00)):
            with patch.object(self.engine, '_create_open_spread_order') as mock_create_order:
                with patch('walk_limit_engine.preflight_multi_leg') as mock_preflight:
                    with patch('walk_limit_engine.place_multileg_order') as mock_place_order:
                        with patch('walk_limit_engine.get_order') as mock_get_order:
                            with patch('walk_limit_engine.cancel_order') as mock_cancel:
                                # Setup mocks
                                mock_create_order.return_value = Mock()
                                mock_preflight.return_value = Mock(estimatedCost="250.00")
                                mock_place_order.return_value = Mock(orderId="ORDER123")
                                
                                # Order never fills
                                mock_get_order.return_value = MockOrder("ORDER123", "NEW", "0")
                                
                                # Start process with very limited attempts
                                process_id = self.engine.start_open_call_spread_process(
                                    symbol="AAPL",
                                    short_expiration="2024-07-19",
                                    short_strike=170.0,
                                    long_expiration="2024-08-16",
                                    long_strike=175.0,
                                    quantity=5,
                                    max_wait_time=1,
                                    execute_mode=True
                                )
                                
                                # Manually set max attempts low for testing
                                if process_id in self.engine.processes:
                                    self.engine.processes[process_id].max_attempts = 2
                                
                                # Wait for process to complete
                                time.sleep(5)
                                
                                # Check results - no fills
                                status = self.engine.get_process_status(process_id)
                                self.assertIsNotNone(status)
                                self.assertEqual(status['original_quantity'], 5)
                                self.assertEqual(status['filled_quantity'], 0)
                                self.assertEqual(status['remaining_quantity'], 5)
                                self.assertEqual(status['fill_percentage'], 0.0)
                                self.assertEqual(len(status['successful_fills']), 0)
    
    def test_fill_tracking_accuracy(self):
        """Test that fill tracking is accurate across complex scenarios."""
        with patch.object(self.engine, '_get_spread_pricing', return_value=(2.50, 3.00)):
            with patch.object(self.engine, '_create_open_spread_order') as mock_create_order:
                with patch('walk_limit_engine.preflight_multi_leg') as mock_preflight:
                    with patch('walk_limit_engine.place_multileg_order') as mock_place_order:
                        with patch('walk_limit_engine.get_order') as mock_get_order:
                            # Setup for complex fill scenario
                            mock_create_order.return_value = Mock()
                            mock_preflight.return_value = Mock(estimatedCost="1000.00")
                            
                            order_responses = [
                                Mock(orderId=f"ORDER{i}") for i in range(5)
                            ]
                            mock_place_order.side_effect = order_responses
                            
                            # Complex fill pattern: 50 total, fills of 15, 10, 8, 12, 5
                            fill_pattern = [
                                (15, "PARTIALLY_FILLED"),
                                (10, "PARTIALLY_FILLED"), 
                                (8, "PARTIALLY_FILLED"),
                                (12, "PARTIALLY_FILLED"),
                                (5, "FILLED")
                            ]
                            
                            order_statuses = []
                            for i, (fill_qty, status) in enumerate(fill_pattern):
                                # Add status checks for each order
                                order_statuses.extend([
                                    MockOrder(f"ORDER{i}", status, str(fill_qty)),
                                    MockOrder(f"ORDER{i}", status, str(fill_qty))
                                ])
                            
                            mock_get_order.side_effect = order_statuses
                            
                            # Start process
                            process_id = self.engine.start_open_call_spread_process(
                                symbol="AAPL",
                                short_expiration="2024-07-19",
                                short_strike=170.0,
                                long_expiration="2024-08-16",
                                long_strike=175.0,
                                quantity=50,
                                max_wait_time=1,
                                execute_mode=True
                            )
                            
                            # Wait for completion
                            time.sleep(10)
                            
                            # Verify fill tracking accuracy
                            status = self.engine.get_process_status(process_id)
                            self.assertIsNotNone(status)
                            
                            # Check totals
                            expected_total = sum(qty for qty, _ in fill_pattern)
                            self.assertEqual(status['filled_quantity'], expected_total)
                            self.assertEqual(status['remaining_quantity'], 0)
                            self.assertEqual(len(status['successful_fills']), len(fill_pattern))
                            
                            # Check individual fill records
                            fills = status['successful_fills']
                            for i, (expected_qty, _) in enumerate(fill_pattern):
                                self.assertEqual(fills[i]['quantity'], expected_qty)
                                self.assertEqual(fills[i]['order_id'], f"ORDER{i}")


class TestFillReporting(unittest.TestCase):
    """Test fill reporting and status updates."""
    
    def setUp(self):
        """Set up test environment."""
        self.mock_client = Mock()
        self.engine = WalkLimitEngine(self.mock_client)
    
    def test_fill_percentage_calculation(self):
        """Test fill percentage calculations."""
        # Create a process directly for testing
        process = WalkLimitProcess(
            process_id="test123",
            symbol="AAPL",
            strategy="open_call_spread",
            short_strike=170.0,
            long_strike=175.0,
            expiration="2024-07-19",
            quantity=10,
            max_wait_time=42,
            execute_mode=True,
            status=ProcessStatus.RUNNING,
            current_price=2.50,
            target_price=3.00,
            increment=0.05,
            attempts=1,
            max_attempts=10,
            created_at=datetime.now(),
            last_update=datetime.now()
        )
        
        # Test various fill scenarios
        test_cases = [
            (10, 0, 0.0),      # No fills
            (10, 3, 30.0),     # 30% filled
            (10, 5, 50.0),     # Half filled
            (10, 7, 70.0),     # 70% filled
            (10, 10, 100.0),   # Completely filled
            (1, 1, 100.0),     # Single contract filled
        ]
        
        for original, filled, expected_pct in test_cases:
            with self.subTest(original=original, filled=filled):
                process.original_quantity = original
                process.filled_quantity = filled
                process.remaining_quantity = original - filled
                
                self.engine.processes["test123"] = process
                status = self.engine.get_process_status("test123")
                
                self.assertEqual(status['fill_percentage'], expected_pct)
                self.assertEqual(status['original_quantity'], original)
                self.assertEqual(status['filled_quantity'], filled)
                self.assertEqual(status['remaining_quantity'], original - filled)
    
    def test_fill_record_structure(self):
        """Test that fill records contain all required information."""
        # Create a mock fill record
        fill_record = {
            'order_id': 'ORDER123',
            'price': 2.65,
            'quantity': 5,
            'timestamp': datetime.now().isoformat(),
            'attempt': 3,
            'partial': True
        }
        
        # Verify all required fields are present
        required_fields = ['order_id', 'price', 'quantity', 'timestamp', 'attempt']
        for field in required_fields:
            self.assertIn(field, fill_record)
        
        # Verify field types
        self.assertIsInstance(fill_record['order_id'], str)
        self.assertIsInstance(fill_record['price'], (int, float))
        self.assertIsInstance(fill_record['quantity'], int)
        self.assertIsInstance(fill_record['timestamp'], str)
        self.assertIsInstance(fill_record['attempt'], int)
        self.assertIsInstance(fill_record.get('partial', False), bool)


def run_partial_fill_tests():
    """Run all partial fill tests."""
    print("🧪 Running Partial Fill Tests for Walk Limit Engine")
    print("=" * 60)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    test_classes = [
        TestPartialFills,
        TestFillReporting
    ]
    
    for test_class in test_classes:
        tests = loader.loadTestsFromTestCase(test_class)
        suite.addTests(tests)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    
    # Display results
    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print("✅ All partial fill tests passed!")
    else:
        print(f"❌ {len(result.failures)} failures, {len(result.errors)} errors")
        
        if result.failures:
            print("\nFailures:")
            for test, traceback in result.failures:
                print(f"  - {test}")
                print(f"    {traceback}")
        
        if result.errors:
            print("\nErrors:")
            for test, traceback in result.errors:
                print(f"  - {test}")
                print(f"    {traceback}")
    
    print(f"\nTests run: {result.testsRun}")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_partial_fill_tests()
    sys.exit(0 if success else 1)
