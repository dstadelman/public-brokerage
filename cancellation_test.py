#!/usr/bin/env python3
"""
Quick test to verify cancellation functionality works correctly.
"""

import unittest
from unittest.mock import Mock, MagicMock
from walk_limit_engine import WalkLimitEngine, WalkLimitProcess, ProcessStatus
from public_brokerage.client import PublicBrokerageClient
from datetime import datetime


class TestCancellation(unittest.TestCase):
    
    def setUp(self):
        # Create mock client
        self.mock_client = Mock(spec=PublicBrokerageClient)
        self.engine = WalkLimitEngine(self.mock_client)
        
        # Create some mock processes with all required fields
        now = datetime.now()
        
        self.process1 = WalkLimitProcess(
            process_id="test1",
            symbol="SPY",
            strategy="open_call_spread",
            short_symbol="SPY   240119C00420000",
            long_symbol="SPY   240119C00425000",
            quantity=10,
            remaining_quantity=10,
            max_wait_time=60,
            execute_mode=True,
            status=ProcessStatus.RUNNING,
            current_price=4.20,
            target_price=4.25,
            increment=0.01,
            attempts=0,
            max_attempts=10,
            created_at=now,
            last_update=now,
            last_order_id="ORDER123"
        )
        
        self.process2 = WalkLimitProcess(
            process_id="test2",
            symbol="AAPL",
            strategy="close_call_spread",
            short_symbol="AAPL  240119C00150000",
            long_symbol="AAPL  240119C00155000",
            quantity=5,
            remaining_quantity=3,
            max_wait_time=60,
            execute_mode=True,
            status=ProcessStatus.WAITING,
            current_price=1.50,
            target_price=1.55,
            increment=0.01,
            attempts=0,
            max_attempts=10,
            created_at=now,
            last_update=now,
            last_order_id="ORDER456"
        )
        
        # Add processes to engine
        self.engine.processes["test1"] = self.process1
        self.engine.processes["test2"] = self.process2
    
    def test_get_active_orders(self):
        """Test getting active orders."""
        active_orders = self.engine.get_active_orders()
        
        # Should return both orders since both processes are active
        self.assertEqual(len(active_orders), 2)
        self.assertIn("test1", active_orders)
        self.assertIn("test2", active_orders)
        self.assertEqual(active_orders["test1"], "ORDER123")
        self.assertEqual(active_orders["test2"], "ORDER456")
    
    def test_get_active_orders_ignores_completed(self):
        """Test that completed processes are ignored."""
        # Mark one process as completed
        self.process1.status = ProcessStatus.COMPLETED
        
        active_orders = self.engine.get_active_orders()
        
        # Should only return the active process
        self.assertEqual(len(active_orders), 1)
        self.assertIn("test2", active_orders)
        self.assertEqual(active_orders["test2"], "ORDER456")
    
    def test_cancel_all_processes_success(self):
        """Test successful cancellation of all processes."""
        with unittest.mock.patch('walk_limit_engine.config.get_default_account', return_value='12345678'):
            with unittest.mock.patch('walk_limit_engine.cancel_order') as mock_cancel:
                count = self.engine.cancel_all_processes()
                
                # Should have cancelled 2 processes
                self.assertEqual(count, 2)
                
                # Should have called cancel_order for both orders
                self.assertEqual(mock_cancel.call_count, 2)
                
                # Both processes should be marked as cancelled
                self.assertEqual(self.process1.status, ProcessStatus.CANCELLED)
                self.assertEqual(self.process2.status, ProcessStatus.CANCELLED)
    
    def test_cancel_all_processes_no_active(self):
        """Test cancelling when no processes are active."""
        # Mark both as completed
        self.process1.status = ProcessStatus.COMPLETED
        self.process2.status = ProcessStatus.CANCELLED
        
        count = self.engine.cancel_all_processes()
        
        # Should return 0 since no active processes
        self.assertEqual(count, 0)


if __name__ == '__main__':
    unittest.main()
