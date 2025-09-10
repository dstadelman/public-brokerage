#!/usr/bin/env python3
"""
Test script for the Public Brokerage Shell system.
Validates all components and their integration.
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, date
import tempfile
import json

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from config import Config
from position_analyzer import PositionAnalyzer, SpreadLeg, CallSpread
from confirmation_card import ConfirmationCard
from walk_limit_engine import WalkLimitEngine, ProcessStatus
from process_manager import ProcessManager, ProcessPriority


class TestConfig(unittest.TestCase):
    """Test configuration management."""
    
    def setUp(self):
        """Set up test with temporary config."""
        self.temp_dir = tempfile.mkdtemp()
        self.config = Config()
        # Override config directory for testing
        self.config.config_dir = os.path.join(self.temp_dir, '.public_brokerage')
        self.config.config_file = os.path.join(self.config.config_dir, 'config.json')
        self.config._ensure_config_dir()
    
    def test_default_config_creation(self):
        """Test default configuration is created properly."""
        self.config.load()
        
        self.assertIsNone(self.config.get_default_account())
        self.assertEqual(self.config.get_max_wait_time(), 42)
        self.assertTrue(self.config.use_colors())
    
    def test_set_default_account(self):
        """Test setting and getting default account."""
        account_id = "TEST123"
        self.config.set_default_account(account_id)
        
        self.assertEqual(self.config.get_default_account(), account_id)
        
        # Verify persistence
        new_config = Config()
        new_config.config_dir = self.config.config_dir
        new_config.config_file = self.config.config_file
        new_config.load()
        
        self.assertEqual(new_config.get_default_account(), account_id)
    
    def test_background_process_management(self):
        """Test background process persistence."""
        process_id = "test_proc_123"
        process_info = {
            'symbol': 'AAPL',
            'strategy': 'open_call_spread',
            'status': 'RUNNING',
            'created_at': datetime.now().isoformat()
        }
        
        self.config.add_background_process(process_id, process_info)
        
        processes = self.config.get_background_processes()
        self.assertIn(process_id, processes)
        self.assertEqual(processes[process_id]['symbol'], 'AAPL')
        
        self.config.remove_background_process(process_id)
        processes = self.config.get_background_processes()
        self.assertNotIn(process_id, processes)


class TestPositionAnalyzer(unittest.TestCase):
    """Test position analysis functionality."""
    
    def setUp(self):
        """Set up test analyzer."""
        self.analyzer = PositionAnalyzer()
    
    def test_extract_underlying_from_option(self):
        """Test underlying symbol extraction."""
        test_cases = [
            ("AAPL240719C00170000", "AAPL"),
            ("SPY240816P00450000", "SPY"),
            ("TSLA250117C00200000", "TSLA"),
            ("QQQ241220C00380000", "QQQ")
        ]
        
        for option_symbol, expected_underlying in test_cases:
            with self.subTest(option_symbol=option_symbol):
                result = self.analyzer._extract_underlying_from_option(option_symbol)
                self.assertEqual(result, expected_underlying)
    
    def test_parse_option_details(self):
        """Test option symbol parsing."""
        option_symbol = "AAPL240719C00170000"
        details = self.analyzer._parse_option_details(option_symbol)
        
        self.assertIsNotNone(details)
        self.assertEqual(details['underlying'], 'AAPL')
        self.assertEqual(details['expiration'], date(2024, 7, 19))
        self.assertEqual(details['option_type'], 'CALL')
        self.assertEqual(details['strike'], 170.0)
    
    @patch('public_brokerage.models.portfolio.Position')
    def test_analyze_positions_empty(self, mock_position):
        """Test analyzing empty positions."""
        positions = []
        result = self.analyzer.analyze_positions(positions)
        
        self.assertEqual(len(result['call_spreads']), 0)
        self.assertEqual(len(result['put_spreads']), 0)
        self.assertEqual(len(result['stocks']), 0)
        self.assertEqual(len(result['unmatched_options']), 0)


class TestConfirmationCard(unittest.TestCase):
    """Test confirmation card functionality."""
    
    def setUp(self):
        """Set up test confirmation card."""
        self.mock_client = Mock()
        self.confirmation_card = ConfirmationCard(self.mock_client)
    
    @patch('public_brokerage.market_data.get_quotes')
    def test_get_underlying_quote(self, mock_get_quotes):
        """Test getting underlying quote."""
        mock_quote = Mock()
        mock_quote.last = 150.25
        mock_quote.change = 2.50
        mock_quote.changePercent = 1.69
        mock_quote.volume = 50000000
        
        mock_get_quotes.return_value = [mock_quote]
        
        result = self.confirmation_card._get_underlying_quote("AAPL")
        
        self.assertIsNotNone(result)
        self.assertEqual(result.last, 150.25)
        mock_get_quotes.assert_called_once_with(self.mock_client, ["AAPL"])
    
    def test_calculate_spread_pricing(self):
        """Test spread pricing calculation."""
        short_option = {
            'bid': 5.00,
            'ask': 5.20
        }
        long_option = {
            'bid': 2.30,
            'ask': 2.50
        }
        
        spread_bid, spread_ask = self.confirmation_card._calculate_spread_pricing(
            short_option, long_option
        )
        
        # For opening: spread_bid = short_bid - long_ask, spread_ask = short_ask - long_bid
        self.assertEqual(spread_bid, 2.50)  # 5.00 - 2.50
        self.assertEqual(spread_ask, 2.90)  # 5.20 - 2.30


class TestWalkLimitEngine(unittest.TestCase):
    """Test walk limit order engine."""
    
    def setUp(self):
        """Set up test engine."""
        self.mock_client = Mock()
        self.engine = WalkLimitEngine(self.mock_client)
    
    def test_process_creation(self):
        """Test process creation and registration."""
        with patch.object(self.engine, '_get_spread_pricing', return_value=(2.50, 3.00)):
            process_id = self.engine.start_open_call_spread_process(
                symbol="AAPL",
                short_expiration="2024-07-19",
                short_strike=170.0,
                long_expiration="2024-08-16",
                long_strike=175.0,
                quantity=1,
                max_wait_time=42,
                execute_mode=False
            )
        
        self.assertIsNotNone(process_id)
        self.assertIn(process_id, self.engine.processes)
        
        process = self.engine.processes[process_id]
        self.assertEqual(process.symbol, "AAPL")
        self.assertEqual(process.strategy, "open_call_spread")
        self.assertEqual(process.quantity, 1)
    
    def test_process_status_tracking(self):
        """Test process status retrieval."""
        with patch.object(self.engine, '_get_spread_pricing', return_value=(2.50, 3.00)):
            process_id = self.engine.start_open_call_spread_process(
                symbol="AAPL",
                short_expiration="2024-07-19",
                short_strike=170.0,
                long_expiration="2024-08-16",
                long_strike=175.0,
                quantity=1,
                execute_mode=False
            )
        
        status = self.engine.get_process_status(process_id)
        
        self.assertIsNotNone(status)
        self.assertEqual(status['symbol'], 'AAPL')
        self.assertEqual(status['strategy'], 'open_call_spread')
        self.assertIn('attempts', status)
        self.assertIn('current_price', status)


class TestProcessManager(unittest.TestCase):
    """Test process manager functionality."""
    
    def setUp(self):
        """Set up test process manager."""
        self.manager = ProcessManager(max_concurrent_processes=5)
    
    def test_process_registration(self):
        """Test process registration."""
        process_id = "test_process_123"
        process_data = {
            'symbol': 'AAPL',
            'strategy': 'open_call_spread'
        }
        
        success = self.manager.register_process(
            process_id,
            'open_call_spread',
            process_data,
            ProcessPriority.NORMAL
        )
        
        self.assertTrue(success)
        self.assertIn(process_id, self.manager.processes)
        
        status = self.manager.get_process_status(process_id)
        self.assertIsNotNone(status)
        self.assertEqual(status['type'], 'open_call_spread')
    
    def test_max_concurrent_limit(self):
        """Test maximum concurrent process limit."""
        # Fill up to max capacity
        for i in range(5):
            success = self.manager.register_process(
                f"process_{i}",
                'test',
                {'test': 'data'},
                ProcessPriority.NORMAL
            )
            self.assertTrue(success)
        
        # Try to register one more (should fail)
        success = self.manager.register_process(
            "process_6",
            'test',
            {'test': 'data'},
            ProcessPriority.NORMAL
        )
        self.assertFalse(success)
    
    def test_system_stats(self):
        """Test system statistics."""
        # Register a few processes
        for i in range(3):
            self.manager.register_process(
                f"process_{i}",
                'test',
                {'test': 'data'}
            )
        
        stats = self.manager.get_system_stats()
        
        self.assertEqual(stats['total_processes'], 3)
        self.assertEqual(stats['max_concurrent'], 5)
        self.assertIn('status_breakdown', stats)


class TestIntegration(unittest.TestCase):
    """Test integration between components."""
    
    def setUp(self):
        """Set up integration test environment."""
        self.mock_client = Mock()
        self.analyzer = PositionAnalyzer()
        self.confirmation_card = ConfirmationCard(self.mock_client)
        self.walk_engine = WalkLimitEngine(self.mock_client)
    
    @patch('public_brokerage.market_data.get_quotes')
    @patch('public_brokerage.market_data.get_option_chain')
    def test_end_to_end_spread_flow(self, mock_get_chain, mock_get_quotes):
        """Test end-to-end flow for opening a spread."""
        # Mock underlying quote
        mock_quote = Mock()
        mock_quote.last = 150.25
        mock_quote.change = 2.50
        mock_quote.changePercent = 1.69
        mock_quote.volume = 50000000
        mock_get_quotes.return_value = [mock_quote]
        
        # Mock option chain
        mock_option_short = Mock()
        mock_option_short.strikePrice = 170.0
        mock_option_short.optionType = 'CALL'
        mock_option_short.bid = 5.00
        mock_option_short.ask = 5.20
        mock_option_short.symbol = 'AAPL240719C00170000'
        
        mock_option_long = Mock()
        mock_option_long.strikePrice = 175.0
        mock_option_long.optionType = 'CALL'
        mock_option_long.bid = 2.30
        mock_option_long.ask = 2.50
        mock_option_long.symbol = 'AAPL240719C00175000'
        
        mock_chain = Mock()
        mock_chain.options = [mock_option_short, mock_option_long]
        mock_get_chain.return_value = mock_chain
        
        # Test getting market data for confirmation
        underlying_quote = self.confirmation_card._get_underlying_quote("AAPL")
        self.assertIsNotNone(underlying_quote)
        self.assertEqual(underlying_quote.last, 150.25)
        
        # Test option data retrieval
        short_data = self.confirmation_card._get_option_data("AAPL", "2024-07-19", 170.0, "CALL")
        self.assertIsNotNone(short_data)
        self.assertEqual(short_data['bid'], 5.00)
        
        # Test spread pricing calculation
        spread_bid, spread_ask = self.confirmation_card._calculate_spread_pricing(short_data, {
            'bid': 2.30, 'ask': 2.50
        })
        self.assertEqual(spread_bid, 2.50)  # 5.00 - 2.50
        self.assertEqual(spread_ask, 2.90)  # 5.20 - 2.30


def run_tests():
    """Run all tests and display results."""
    print("🧪 Running Public Brokerage Shell Tests")
    print("=" * 50)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test cases
    test_classes = [
        TestConfig,
        TestPositionAnalyzer,
        TestConfirmationCard,
        TestWalkLimitEngine,
        TestProcessManager,
        TestIntegration
    ]
    
    for test_class in test_classes:
        tests = loader.loadTestsFromTestCase(test_class)
        suite.addTests(tests)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    
    # Display results
    print("\n" + "=" * 50)
    if result.wasSuccessful():
        print("✅ All tests passed!")
    else:
        print(f"❌ {len(result.failures)} failures, {len(result.errors)} errors")
        
        if result.failures:
            print("\nFailures:")
            for test, traceback in result.failures:
                print(f"  - {test}: {traceback}")
        
        if result.errors:
            print("\nErrors:")
            for test, traceback in result.errors:
                print(f"  - {test}: {traceback}")
    
    print(f"\nTests run: {result.testsRun}")
    print(f"Execution time: {result.time if hasattr(result, 'time') else 'N/A'}s")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
