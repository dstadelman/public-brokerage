#!/usr/bin/env python3
"""
Demonstration script showing partial fill handling in the walk limit engine.
This script simulates various partial fill scenarios to demonstrate the enhanced
tracking and reporting capabilities.
"""

import os
import sys
import time
from datetime import datetime

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from walk_limit_engine import WalkLimitEngine, ProcessStatus, WalkLimitProcess


def simulate_partial_fill_scenario():
    """
    Simulate a realistic partial fill scenario showing the enhanced tracking.
    """
    print("🎯 Partial Fill Scenario Demonstration")
    print("=" * 60)
    
    # Create a mock client
    class MockClient:
        def __init__(self):
            self.orders = {}
            self.order_counter = 1000
        
        def _make_request(self, method, endpoint, data=None):
            pass
    
    # Initialize engine
    client = MockClient()
    engine = WalkLimitEngine(client)
    
    # Create a sample process with partial fills
    process = WalkLimitProcess(
        process_id="DEMO_001",
        symbol="AAPL",
        strategy="open_call_spread",
        short_strike=170.0,
        long_strike=175.0,
        expiration="2024-07-19",
        quantity=20,  # Original order quantity
        max_wait_time=60,
        execute_mode=True,
        status=ProcessStatus.COMPLETED,
        current_price=2.50,
        target_price=3.00,
        increment=0.05,
        attempts=4,
        max_attempts=10,
        created_at=datetime.now(),
        last_update=datetime.now()
    )
    
    # Simulate partial fills across multiple orders
    # Scenario: 20 contracts requested, filled in 4 orders: 7, 5, 3, 5
    process.filled_quantity = 20
    process.remaining_quantity = 0
    process.successful_fills = [
        {
            'order_id': 'ORDER_1001',
            'price': 2.55,
            'quantity': 7,
            'timestamp': '2024-07-19T10:15:30Z',
            'attempt': 1,
            'partial': True
        },
        {
            'order_id': 'ORDER_1002', 
            'price': 2.60,
            'quantity': 5,
            'timestamp': '2024-07-19T10:18:45Z',
            'attempt': 2,
            'partial': True
        },
        {
            'order_id': 'ORDER_1003',
            'price': 2.65,
            'quantity': 3,
            'timestamp': '2024-07-19T10:22:15Z',
            'attempt': 3,
            'partial': True
        },
        {
            'order_id': 'ORDER_1004',
            'price': 2.70,
            'quantity': 5,
            'timestamp': '2024-07-19T10:25:30Z',
            'attempt': 4,
            'partial': False  # Final fill completed the order
        }
    ]
    
    # Add process to engine
    engine.processes["DEMO_001"] = process
    
    # Display comprehensive status
    status = engine.get_process_status("DEMO_001")
    
    print(f"📋 Process Status Report")
    print(f"Process ID: {status['process_id']}")
    print(f"Symbol: {status['symbol']}")
    print(f"Strategy: {status['strategy']}")
    print(f"Status: {status['status']}")
    print()
    
    print(f"📊 Fill Summary:")
    print(f"  Original Quantity: {status['original_quantity']:,} contracts")
    print(f"  Filled Quantity:   {status['filled_quantity']:,} contracts")
    print(f"  Remaining:         {status['remaining_quantity']:,} contracts")
    print(f"  Fill Percentage:   {status['fill_percentage']:.1f}%")
    print(f"  Total Attempts:    {status['attempts']}")
    print(f"  Successful Fills:  {len(status['successful_fills'])}")
    print()
    
    print(f"💰 Fill Details:")
    total_cost = 0
    for i, fill in enumerate(status['successful_fills'], 1):
        fill_cost = fill['price'] * fill['quantity'] * 100  # $100 per contract
        total_cost += fill_cost
        partial_indicator = " (Partial)" if fill.get('partial') else " (Complete)"
        
        print(f"  Fill #{i}:")
        print(f"    Order ID:   {fill['order_id']}")
        print(f"    Quantity:   {fill['quantity']:,} contracts")
        print(f"    Price:      ${fill['price']:.2f}")
        print(f"    Cost:       ${fill_cost:,.2f}{partial_indicator}")
        print(f"    Time:       {fill['timestamp']}")
        print(f"    Attempt:    {fill['attempt']}")
        print()
    
    print(f"💵 Total Investment: ${total_cost:,.2f}")
    print(f"📈 Average Fill Price: ${total_cost / (status['filled_quantity'] * 100):.2f}")
    
    return status


def demonstrate_incomplete_fills():
    """
    Demonstrate a scenario where not all contracts are filled.
    """
    print("\n🚧 Incomplete Fill Scenario")
    print("=" * 60)
    
    # Create another mock scenario
    class MockClient:
        pass
    
    client = MockClient()
    engine = WalkLimitEngine(client)
    
    # Process that only partially filled before reaching max attempts
    process = WalkLimitProcess(
        process_id="DEMO_002",
        symbol="SPY",
        strategy="close_put_spread",
        short_strike=430.0,
        long_strike=425.0,
        expiration="2024-08-16",
        quantity=15,  # Wanted 15 contracts
        max_wait_time=45,
        execute_mode=True,
        status=ProcessStatus.FAILED,
        current_price=1.80,
        target_price=1.50,
        increment=0.05,
        attempts=8,
        max_attempts=8,
        created_at=datetime.now(),
        last_update=datetime.now()
    )
    
    # Only got partial fills - 8 out of 15 contracts
    process.filled_quantity = 8
    process.remaining_quantity = 7
    process.successful_fills = [
        {
            'order_id': 'CLOSE_2001',
            'price': 1.85,
            'quantity': 3,
            'timestamp': '2024-08-16T14:30:15Z',
            'attempt': 2,
            'partial': True
        },
        {
            'order_id': 'CLOSE_2002',
            'price': 1.80,
            'quantity': 5,
            'timestamp': '2024-08-16T14:35:45Z',
            'attempt': 5,
            'partial': True
        }
    ]
    
    engine.processes["DEMO_002"] = process
    status = engine.get_process_status("DEMO_002")
    
    print(f"📋 Incomplete Process Status:")
    print(f"Process ID: {status['process_id']}")
    print(f"Symbol: {status['symbol']}")
    print(f"Strategy: {status['strategy']}")
    print(f"Status: {status['status']} ❌")
    print()
    
    print(f"📊 Partial Fill Summary:")
    print(f"  Requested:   {status['original_quantity']:,} contracts")
    print(f"  Filled:      {status['filled_quantity']:,} contracts ✅")
    print(f"  Remaining:   {status['remaining_quantity']:,} contracts ⏳")
    print(f"  Success:     {status['fill_percentage']:.1f}%")
    print(f"  Attempts:    {status['attempts']}/{process.max_attempts}")
    print()
    
    print(f"💡 Analysis:")
    print(f"  • Successfully closed {status['filled_quantity']} out of {status['original_quantity']} spread contracts")
    print(f"  • Still holding {status['remaining_quantity']} contracts in the position")
    print(f"  • May need manual intervention or retry with different parameters")
    print(f"  • Process stopped after reaching maximum attempts")
    
    return status


def show_fill_tracking_benefits():
    """
    Show the benefits of the enhanced fill tracking system.
    """
    print("\n🎯 Enhanced Fill Tracking Benefits")
    print("=" * 60)
    
    benefits = [
        "✅ Accurate Quantity Tracking: Know exactly how many contracts were filled vs. remaining",
        "📊 Fill Percentage Monitoring: Real-time completion status for all processes", 
        "💰 Cost Basis Calculation: Track average fill prices across multiple partial orders",
        "🕐 Timing Analysis: See when each fill occurred for performance analysis",
        "🔄 Process Recovery: Resume processes from exact fill state after interruptions",
        "📈 Performance Metrics: Analyze fill rates and pricing efficiency",
        "⚠️  Risk Management: Know exact position sizes after partial executions",
        "🎯 Strategy Optimization: Data-driven insights for improving fill rates"
    ]
    
    for benefit in benefits:
        print(f"  {benefit}")
    
    print(f"\n🔧 Technical Implementation:")
    print(f"  • WalkLimitProcess enhanced with fill tracking fields")
    print(f"  • _wait_for_fill method returns detailed fill status")
    print(f"  • Process status includes comprehensive fill information")
    print(f"  • All partial fills preserved in successful_fills array")
    print(f"  • Remaining quantity calculated and updated automatically")


def main():
    """
    Run the partial fill demonstration.
    """
    print("🚀 Public Brokerage Walk Limit Engine")
    print("Partial Fill Handling Demonstration")
    print("=" * 60)
    
    # Run demonstrations
    complete_scenario = simulate_partial_fill_scenario()
    incomplete_scenario = demonstrate_incomplete_fills()
    show_fill_tracking_benefits()
    
    print(f"\n🏁 Demonstration Complete")
    print(f"Enhanced partial fill handling provides comprehensive tracking")
    print(f"and reporting for production trading operations.")
    
    return True


if __name__ == "__main__":
    main()
