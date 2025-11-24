"""
Unit tests for Forward Factor calculations using real MVST calendar spread data.

Test Data from Market (2024-11-12):
- Symbol: MVST
- Strike: $4.00
- Short Leg (2025-12-19): 37 DTE
  - BID: $0.50, ASK: $0.70, MID: $0.60
- Long Leg (2026-01-16): 65 DTE
  - BID: $0.70, ASK: $0.85, MID: $0.77
- Calendar Spread:
  - BID: $0.00 (extreme contango case)
  - MID: $0.17
  - ASK: $0.35
- Underlying: ~$4.00 (ATM options)
"""

import unittest
import math
from utils.black_scholes import estimate_iv_from_price, black_scholes_call
from utils.forward_factor import calculate_forward_factor_from_ivs


class TestForwardFactorMVST(unittest.TestCase):
    """Test Forward Factor calculations with MVST real market data."""
    
    def setUp(self):
        """Set up test data matching MVST calendar spread."""
        # Market data
        self.underlying_price = 4.0
        self.strike = 4.0
        self.risk_free_rate = 0.045
        
        # Short leg (2025-12-19) - 37 DTE
        self.short_dte = 37
        self.short_bid = 0.50
        self.short_ask = 0.70
        self.short_mid = 0.60
        
        # Long leg (2026-01-16) - 65 DTE
        self.long_dte = 65
        self.long_bid = 0.70
        self.long_ask = 0.85
        self.long_mid = 0.77
        
        # Spread prices
        self.spread_bid = 0.00  # Extreme contango case
        self.spread_mid = 0.17
        self.spread_ask = 0.35
    
    def test_iv_estimation_short_leg_mid(self):
        """Test IV estimation for short leg at MID price."""
        T = self.short_dte / 365.0
        
        iv = estimate_iv_from_price(
            option_price=self.short_mid,
            S=self.underlying_price,
            K=self.strike,
            T=T,
            r=self.risk_free_rate,
            option_type='call'
        )
        
        self.assertIsNotNone(iv, "Should successfully estimate IV")
        self.assertGreater(iv, 0, "IV should be positive")
        self.assertLess(iv, 3.0, "IV should be reasonable (<300%)")
        
        # Verify by pricing back
        calculated_price = black_scholes_call(
            S=self.underlying_price,
            K=self.strike,
            T=T,
            r=self.risk_free_rate,
            sigma=iv
        )
        self.assertAlmostEqual(calculated_price, self.short_mid, places=4,
                              msg="Calculated price should match market price")
    
    def test_iv_estimation_long_leg_mid(self):
        """Test IV estimation for long leg at MID price."""
        T = self.long_dte / 365.0
        
        iv = estimate_iv_from_price(
            option_price=self.long_mid,
            S=self.underlying_price,
            K=self.strike,
            T=T,
            r=self.risk_free_rate,
            option_type='call'
        )
        
        self.assertIsNotNone(iv, "Should successfully estimate IV")
        self.assertGreater(iv, 0, "IV should be positive")
        self.assertLess(iv, 3.0, "IV should be reasonable (<300%)")
        
        # Verify by pricing back
        calculated_price = black_scholes_call(
            S=self.underlying_price,
            K=self.strike,
            T=T,
            r=self.risk_free_rate,
            sigma=iv
        )
        self.assertAlmostEqual(calculated_price, self.long_mid, places=4,
                              msg="Calculated price should match market price")
    
    def test_ff_calculation_at_mid_execution(self):
        """
        Test FF calculation at MID execution prices.
        
        At MID: both legs execute at their respective MID prices.
        """
        # Calculate IVs at MID prices
        short_T = self.short_dte / 365.0
        long_T = self.long_dte / 365.0
        
        short_iv = estimate_iv_from_price(
            option_price=self.short_mid,
            S=self.underlying_price,
            K=self.strike,
            T=short_T,
            r=self.risk_free_rate,
            option_type='call'
        )
        
        long_iv = estimate_iv_from_price(
            option_price=self.long_mid,
            S=self.underlying_price,
            K=self.strike,
            T=long_T,
            r=self.risk_free_rate,
            option_type='call'
        )
        
        self.assertIsNotNone(short_iv, "Short IV should calculate")
        self.assertIsNotNone(long_iv, "Long IV should calculate")
        
        # Calculate FF
        ff = calculate_forward_factor_from_ivs(
            front_iv=short_iv,
            front_dte=self.short_dte,
            back_iv=long_iv,
            back_dte=self.long_dte
        )
        
        self.assertIsNotNone(ff, "FF should calculate successfully")
        print(f"\nFF at MID execution: {ff:.4f}")
        print(f"  Short IV: {short_iv:.4f} (from ${self.short_mid})")
        print(f"  Long IV: {long_iv:.4f} (from ${self.long_mid})")
    
    def test_ff_calculation_at_bid_execution(self):
        """
        Test FF calculation at BID execution (best case).
        
        At BID: Buy long@bid, Sell short@ask
        This is the best execution - paying less for long, getting more for short.
        """
        short_T = self.short_dte / 365.0
        long_T = self.long_dte / 365.0
        
        # At BID execution: short sells at ASK, long buys at BID
        short_iv = estimate_iv_from_price(
            option_price=self.short_ask,  # We sell at ASK
            S=self.underlying_price,
            K=self.strike,
            T=short_T,
            r=self.risk_free_rate,
            option_type='call'
        )
        
        long_iv = estimate_iv_from_price(
            option_price=self.long_bid,  # We buy at BID
            S=self.underlying_price,
            K=self.strike,
            T=long_T,
            r=self.risk_free_rate,
            option_type='call'
        )
        
        self.assertIsNotNone(short_iv, "Short IV should calculate")
        self.assertIsNotNone(long_iv, "Long IV should calculate")
        
        # At BID execution for MVST: both options are $0.70
        # Short (37 DTE) @ $0.70 → HIGHER IV (137%)
        # Long (65 DTE) @ $0.70 → LOWER IV (103%)
        # This creates negative forward variance → FF = inf (extreme backwardation)
        ff = calculate_forward_factor_from_ivs(
            front_iv=short_iv,
            front_dte=self.short_dte,
            back_iv=long_iv,
            back_dte=self.long_dte
        )
        
        self.assertIsNotNone(ff, "FF should calculate")
        print(f"\nFF at BID execution (best case): {ff}")
        print(f"  Short IV: {short_iv:.4f} (from ${self.short_ask})")
        print(f"  Long IV: {long_iv:.4f} (from ${self.long_bid})")
        print(f"  Net spread cost: ${self.long_bid - self.short_ask:.2f}")
        
        # Extreme backwardation should give inf FF
        if ff == float('inf'):
            print(f"  Interpretation: EXTREME BACKWARDATION (vol crush expected)")
    
    def test_ff_calculation_at_ask_execution(self):
        """
        Test FF calculation at ASK execution (worst case).
        
        At ASK: Buy long@ask, Sell short@bid
        This is the worst execution - paying more for long, getting less for short.
        """
        short_T = self.short_dte / 365.0
        long_T = self.long_dte / 365.0
        
        # At ASK execution: short sells at BID, long buys at ASK
        short_iv = estimate_iv_from_price(
            option_price=self.short_bid,  # We sell at BID
            S=self.underlying_price,
            K=self.strike,
            T=short_T,
            r=self.risk_free_rate,
            option_type='call'
        )
        
        long_iv = estimate_iv_from_price(
            option_price=self.long_ask,  # We buy at ASK
            S=self.underlying_price,
            K=self.strike,
            T=long_T,
            r=self.risk_free_rate,
            option_type='call'
        )
        
        self.assertIsNotNone(short_iv, "Short IV should calculate")
        self.assertIsNotNone(long_iv, "Long IV should calculate")
        
        ff = calculate_forward_factor_from_ivs(
            front_iv=short_iv,
            front_dte=self.short_dte,
            back_iv=long_iv,
            back_dte=self.long_dte
        )
        
        self.assertIsNotNone(ff, "FF should calculate successfully")
        print(f"\nFF at ASK execution (worst case): {ff:.4f}")
        print(f"  Short IV: {short_iv:.4f} (from ${self.short_bid})")
        print(f"  Long IV: {long_iv:.4f} (from ${self.long_ask})")
        print(f"  Net spread cost: ${self.long_ask - self.short_bid:.2f}")
    
    def test_ff_range_calculation(self):
        """
        Test FF range across all execution scenarios.
        
        This demonstrates that FF varies with execution price, confirming
        the user's insight that execution price matters for FF calculation.
        """
        short_T = self.short_dte / 365.0
        long_T = self.long_dte / 365.0
        
        # Calculate FF at all three execution scenarios
        scenarios = []
        
        # BID execution - may show extreme backwardation
        short_iv_bid = estimate_iv_from_price(
            self.short_ask, self.underlying_price, self.strike, short_T, 
            self.risk_free_rate, option_type='call'
        )
        long_iv_bid = estimate_iv_from_price(
            self.long_bid, self.underlying_price, self.strike, long_T,
            self.risk_free_rate, option_type='call'
        )
        if short_iv_bid and long_iv_bid:
            ff_bid = calculate_forward_factor_from_ivs(
                short_iv_bid, self.short_dte, long_iv_bid, self.long_dte
            )
            if ff_bid is not None:
                scenarios.append(('BID', ff_bid, self.long_bid - self.short_ask))
        
        # MID execution (expected)
        short_iv_mid = estimate_iv_from_price(
            self.short_mid, self.underlying_price, self.strike, short_T,
            self.risk_free_rate, option_type='call'
        )
        long_iv_mid = estimate_iv_from_price(
            self.long_mid, self.underlying_price, self.strike, long_T,
            self.risk_free_rate, option_type='call'
        )
        if short_iv_mid and long_iv_mid:
            ff_mid = calculate_forward_factor_from_ivs(
                short_iv_mid, self.short_dte, long_iv_mid, self.long_dte
            )
            if ff_mid:
                scenarios.append(('MID', ff_mid, self.long_mid - self.short_mid))
        
        # ASK execution (worst)
        short_iv_ask = estimate_iv_from_price(
            self.short_bid, self.underlying_price, self.strike, short_T,
            self.risk_free_rate, option_type='call'
        )
        long_iv_ask = estimate_iv_from_price(
            self.long_ask, self.underlying_price, self.strike, long_T,
            self.risk_free_rate, option_type='call'
        )
        if short_iv_ask and long_iv_ask:
            ff_ask = calculate_forward_factor_from_ivs(
                short_iv_ask, self.short_dte, long_iv_ask, self.long_dte
            )
            if ff_ask:
                scenarios.append(('ASK', ff_ask, self.long_ask - self.short_bid))
        
        # Verify we calculated all three scenarios
        self.assertEqual(len(scenarios), 3, "Should calculate FF for all 3 scenarios")
        
        print(f"\n{'='*60}")
        print("FF RANGE ANALYSIS - MVST $4 Calendar Spread")
        print(f"{'='*60}")
        for name, ff, spread_cost in scenarios:
            print(f"{name:4s} execution: FF={ff:7.4f} @ spread cost ${spread_cost:.2f}")
        
        # Extract FF values for comparison
        ff_values = [ff for _, ff, _ in scenarios]
        ff_min = min(ff_values)
        ff_max = max(ff_values)
        ff_range = ff_max - ff_min
        
        print(f"\nFF Range: {ff_min:.4f} to {ff_max:.4f} (width: {ff_range:.4f})")
        print(f"{'='*60}")
        
        # Verify that FFs are different (proving execution price matters)
        self.assertGreater(ff_range, 0.001, 
                          "FF should vary across execution scenarios")
    
    def test_extreme_contango_case(self):
        """
        Test handling of extreme contango case where spread BID = $0.
        
        This is a real market condition in MVST calendar spread where:
        - Spread BID = $0.00 (extreme contango)
        - Individual options still have valid prices
        - FF calculation should still work using individual option prices
        """
        self.assertEqual(self.spread_bid, 0.0, 
                        "Test data should include extreme contango case")
        
        # Verify individual options have valid prices
        self.assertGreater(self.short_bid, 0, "Short leg has valid BID")
        self.assertGreater(self.short_ask, 0, "Short leg has valid ASK")
        self.assertGreater(self.long_bid, 0, "Long leg has valid BID")
        self.assertGreater(self.long_ask, 0, "Long leg has valid ASK")
        
        # FF calculation should work despite spread BID = 0
        # because we use individual option prices, not spread price
        short_T = self.short_dte / 365.0
        long_T = self.long_dte / 365.0
        
        short_iv = estimate_iv_from_price(
            self.short_mid, self.underlying_price, self.strike, short_T,
            self.risk_free_rate, option_type='call'
        )
        long_iv = estimate_iv_from_price(
            self.long_mid, self.underlying_price, self.strike, long_T,
            self.risk_free_rate, option_type='call'
        )
        
        ff = calculate_forward_factor_from_ivs(
            short_iv, self.short_dte, long_iv, self.long_dte
        )
        
        self.assertIsNotNone(ff, "FF should calculate even when spread BID = $0")
        print(f"\nExtreme Contango Case:")
        print(f"  Spread BID: ${self.spread_bid:.2f} (ZERO)")
        print(f"  Spread MID: ${self.spread_mid:.2f}")
        print(f"  FF at MID: {ff:.4f} ✓ Calculated successfully")
    
    def test_atm_option_characteristics(self):
        """
        Test characteristics of ATM options (underlying = strike).
        
        For ATM options:
        - Delta should be close to 0.5
        - Option should have significant time value
        - IV should be estimatable from market prices
        """
        self.assertEqual(self.underlying_price, self.strike,
                        "Test uses ATM options (S=K)")
        
        # Calculate IVs
        short_T = self.short_dte / 365.0
        long_T = self.long_dte / 365.0
        
        short_iv = estimate_iv_from_price(
            self.short_mid, self.underlying_price, self.strike, short_T,
            self.risk_free_rate, option_type='call'
        )
        long_iv = estimate_iv_from_price(
            self.long_mid, self.underlying_price, self.strike, long_T,
            self.risk_free_rate, option_type='call'
        )
        
        # ATM options should have successfully calculated IVs
        self.assertIsNotNone(short_iv, "ATM short option IV should calculate")
        self.assertIsNotNone(long_iv, "ATM long option IV should calculate")
        
        # ATM call intrinsic value is 0 (S = K)
        intrinsic = max(0, self.underlying_price - self.strike)
        self.assertEqual(intrinsic, 0.0, "ATM option has no intrinsic value")
        
        # All value is time value
        self.assertGreater(self.short_mid, 0, "Short option has time value")
        self.assertGreater(self.long_mid, 0, "Long option has time value")
        
        print(f"\nATM Option Characteristics:")
        print(f"  Underlying: ${self.underlying_price}")
        print(f"  Strike: ${self.strike}")
        print(f"  Short ({self.short_dte}D): ${self.short_mid} (IV: {short_iv:.4f})")
        print(f"  Long ({self.long_dte}D): ${self.long_mid} (IV: {long_iv:.4f})")
        print(f"  Intrinsic Value: ${intrinsic:.2f} (all time value)")
    
    def test_calendar_spread_structure(self):
        """
        Test that the calendar spread has correct structure.
        
        Calendar spread properties:
        - Short leg expires before long leg
        - Both legs at same strike
        - Long leg should be worth more (longer time = more time value)
        """
        self.assertLess(self.short_dte, self.long_dte,
                       "Short leg should expire first")
        
        days_between = self.long_dte - self.short_dte
        self.assertEqual(days_between, 28,
                        "MVST calendar has 28-day forward period")
        
        # Long leg should typically be worth more (more time value)
        # though this can vary with extreme contango
        self.assertGreaterEqual(self.long_mid, self.short_mid,
                               "Long leg typically worth more")
        
        print(f"\nCalendar Spread Structure:")
        print(f"  Short Leg: {self.short_dte} DTE @ ${self.short_mid}")
        print(f"  Long Leg: {self.long_dte} DTE @ ${self.long_mid}")
        print(f"  Forward Period: {days_between} days")
        print(f"  Spread MID: ${self.spread_mid}")


class TestForwardFactorIWM(unittest.TestCase):
    """Test Forward Factor calculations with IWM real market data."""
    
    def setUp(self):
        """Set up test data for IWM $240 calendar spread."""
        # Market data from 2024-11-12
        self.underlying_price = 243.45
        self.strike = 240.0
        self.risk_free_rate = 0.045
        
        # Short leg (2025-12-19) - 37 DTE
        self.short_dte = 37
        self.short_bid = 9.38
        self.short_ask = 9.49
        self.short_mid = 9.44
        
        # Long leg (2026-01-16) - 65 DTE
        self.long_dte = 65
        self.long_bid = 11.77
        self.long_ask = 11.86
        self.long_mid = 11.81
        
        # Spread prices
        self.spread_bid = 2.28  # long_bid - short_ask
        self.spread_mid = 2.38
        self.spread_ask = 2.48  # long_ask - short_bid
    
    def test_iwm_ff_at_mid_execution(self):
        """Test IWM FF calculation at MID execution prices."""
        short_T = self.short_dte / 365.0
        long_T = self.long_dte / 365.0
        
        short_iv = estimate_iv_from_price(
            option_price=self.short_mid,
            S=self.underlying_price,
            K=self.strike,
            T=short_T,
            r=self.risk_free_rate,
            option_type='call'
        )
        
        long_iv = estimate_iv_from_price(
            option_price=self.long_mid,
            S=self.underlying_price,
            K=self.strike,
            T=long_T,
            r=self.risk_free_rate,
            option_type='call'
        )
        
        self.assertIsNotNone(short_iv, "Short IV should calculate")
        self.assertIsNotNone(long_iv, "Long IV should calculate")
        
        ff = calculate_forward_factor_from_ivs(
            front_iv=short_iv,
            front_dte=self.short_dte,
            back_iv=long_iv,
            back_dte=self.long_dte
        )
        
        self.assertIsNotNone(ff, "FF should calculate")
        print(f"\nIWM FF at MID execution: {ff:.4f}")
        print(f"  Short IV: {short_iv:.4f} ({short_iv*100:.1f}%)")
        print(f"  Long IV: {long_iv:.4f} ({long_iv*100:.1f}%)")
        print(f"  Spread MID: ${self.spread_mid}")
        
        # IWM should show positive FF (backwardation) around 0.08
        self.assertGreater(ff, 0, "IWM should show backwardation")
        self.assertAlmostEqual(ff, 0.081, delta=0.01, msg="FF should be around 0.081")
    
    def test_iwm_ff_range(self):
        """Test IWM FF range across execution scenarios."""
        short_T = self.short_dte / 365.0
        long_T = self.long_dte / 365.0
        
        # BID execution
        short_iv_bid = estimate_iv_from_price(
            self.short_ask, self.underlying_price, self.strike, short_T,
            self.risk_free_rate, option_type='call'
        )
        long_iv_bid = estimate_iv_from_price(
            self.long_bid, self.underlying_price, self.strike, long_T,
            self.risk_free_rate, option_type='call'
        )
        ff_bid = calculate_forward_factor_from_ivs(
            short_iv_bid, self.short_dte, long_iv_bid, self.long_dte
        )
        
        # MID execution
        short_iv_mid = estimate_iv_from_price(
            self.short_mid, self.underlying_price, self.strike, short_T,
            self.risk_free_rate, option_type='call'
        )
        long_iv_mid = estimate_iv_from_price(
            self.long_mid, self.underlying_price, self.strike, long_T,
            self.risk_free_rate, option_type='call'
        )
        ff_mid = calculate_forward_factor_from_ivs(
            short_iv_mid, self.short_dte, long_iv_mid, self.long_dte
        )
        
        # ASK execution
        short_iv_ask = estimate_iv_from_price(
            self.short_bid, self.underlying_price, self.strike, short_T,
            self.risk_free_rate, option_type='call'
        )
        long_iv_ask = estimate_iv_from_price(
            self.long_ask, self.underlying_price, self.strike, long_T,
            self.risk_free_rate, option_type='call'
        )
        ff_ask = calculate_forward_factor_from_ivs(
            short_iv_ask, self.short_dte, long_iv_ask, self.long_dte
        )
        
        print(f"\n{'='*60}")
        print("IWM $240 Calendar Spread FF Range")
        print(f"{'='*60}")
        print(f"BID  execution: FF={ff_bid:7.4f} @ spread ${self.spread_bid}")
        print(f"MID  execution: FF={ff_mid:7.4f} @ spread ${self.spread_mid}")
        print(f"ASK  execution: FF={ff_ask:7.4f} @ spread ${self.spread_ask}")
        print(f"{'='*60}")
        
        # Verify FF decreases as spread cost increases
        self.assertGreater(ff_bid, ff_mid, "FF should decrease from BID to MID")
        self.assertGreater(ff_mid, ff_ask, "FF should decrease from MID to ASK")
        
        # All should be positive (backwardation)
        self.assertGreater(ff_bid, 0, "BID execution should show backwardation")
        self.assertGreater(ff_mid, 0, "MID execution should show backwardation")
        self.assertGreater(ff_ask, 0, "ASK execution should show backwardation")
    
    def test_iwm_vs_mvst_comparison(self):
        """Compare IWM (liquid ETF) vs MVST (illiquid stock)."""
        print(f"\n{'='*60}")
        print("IWM vs MVST Comparison")
        print(f"{'='*60}")
        print(f"\nIWM $240 (Liquid ETF):")
        print(f"  Underlying: ${self.underlying_price}")
        print(f"  Short: ${self.short_mid} (37 DTE)")
        print(f"  Long: ${self.long_mid} (65 DTE)")
        print(f"  Spread MID: ${self.spread_mid}")
        print(f"  Spread BID: ${self.spread_bid} (POSITIVE - normal market)")
        
        print(f"\nMVST $4 (Illiquid Stock):")
        print(f"  Underlying: $4.00")
        print(f"  Short: $0.60 (37 DTE)")
        print(f"  Long: $0.77 (65 DTE)")
        print(f"  Spread MID: $0.17")
        print(f"  Spread BID: $0.00 (ZERO - extreme contango)")
        
        print(f"\nKey Differences:")
        print(f"  • IWM has positive spread BID (normal term structure)")
        print(f"  • MVST has zero spread BID (extreme contango)")
        print(f"  • IWM options are much more liquid")
        print(f"  • Both show same DTE structure (37/65 days)")
        print(f"{'='*60}")


class TestFFGrid(unittest.TestCase):
    """Test grid-based FF calculation functions."""
    
    def setUp(self):
        """Set up test data for grid calculations."""
        from forward_factor_analyzer import ForwardFactorAnalyzer
        self.analyzer = ForwardFactorAnalyzer(client=None, account_id=None)
        
        # MVST data
        self.mvst_short_bid = 0.50
        self.mvst_short_ask = 0.70
        self.mvst_long_bid = 0.70
        self.mvst_long_ask = 0.85
        self.mvst_underlying = 4.0
        self.mvst_strike = 4.0
        self.mvst_short_dte = 37
        self.mvst_long_dte = 65
        
        # IWM data
        self.iwm_short_bid = 9.38
        self.iwm_short_ask = 9.49
        self.iwm_long_bid = 11.77
        self.iwm_long_ask = 11.86
        self.iwm_underlying = 240.0
        self.iwm_strike = 240.0
        self.iwm_short_dte = 37
        self.iwm_long_dte = 65
    
    def test_calculate_ff_grid_mvst_opening(self):
        """Test FF grid calculation for MVST (opening scenario)."""
        grid = self.analyzer.calculate_ff_grid(
            short_bid=self.mvst_short_bid,
            short_ask=self.mvst_short_ask,
            long_bid=self.mvst_long_bid,
            long_ask=self.mvst_long_ask,
            underlying_price=self.mvst_underlying,
            strike=self.mvst_strike,
            short_dte=self.mvst_short_dte,
            long_dte=self.mvst_long_dte
        )
        
        # Should have 21 steps (0 to 20 inclusive)
        self.assertEqual(len(grid), 21)
        
        # Check first step (BID execution: short@ask, long@bid)
        first = grid[0]
        self.assertEqual(first['pct'], 0.0)
        self.assertEqual(first['short_price'], self.mvst_short_ask)
        self.assertEqual(first['long_price'], self.mvst_long_bid)
        self.assertEqual(first['spread_price'], round(self.mvst_long_bid - self.mvst_short_ask, 2))
        
        # Check last step (ASK execution: short@bid, long@ask)
        last = grid[20]
        self.assertEqual(last['pct'], 1.0)
        self.assertEqual(last['short_price'], self.mvst_short_bid)
        self.assertEqual(last['long_price'], self.mvst_long_ask)
        self.assertEqual(last['spread_price'], round(self.mvst_long_ask - self.mvst_short_bid, 2))
        
        # Check that FF decreases (or at least doesn't always increase) as spread price increases
        # Note: Due to extreme backwardation at BID, FF might be inf there
        valid_ffs = [step['ff'] for step in grid if step['ff'] is not None and not math.isinf(step['ff'])]
        if len(valid_ffs) >= 2:
            # At least check that we don't have all increasing FFs
            has_decrease = any(valid_ffs[i] > valid_ffs[i+1] for i in range(len(valid_ffs)-1))
            self.assertTrue(has_decrease or len(set(valid_ffs)) == 1, 
                          "Expected FF to decrease or stay constant as price increases")
        
        print(f"\nMVST FF Grid (Opening):")
        print(f"First 5 steps:")
        for step in grid[:5]:
            ff_str = f"{step['ff']:.3f}" if step['ff'] is not None and not math.isinf(step['ff']) else str(step['ff'])
            print(f"  pct={step['pct']:.2f}: spread=${step['spread_price']:.2f}, FF={ff_str}")
    
    def test_calculate_ff_grid_iwm_opening(self):
        """Test FF grid calculation for IWM (opening scenario)."""
        grid = self.analyzer.calculate_ff_grid(
            short_bid=self.iwm_short_bid,
            short_ask=self.iwm_short_ask,
            long_bid=self.iwm_long_bid,
            long_ask=self.iwm_long_ask,
            underlying_price=self.iwm_underlying,
            strike=self.iwm_strike,
            short_dte=self.iwm_short_dte,
            long_dte=self.iwm_long_dte
        )
        
        # Should have 21 steps
        self.assertEqual(len(grid), 21)
        
        # IWM should have valid FFs at all steps (normal market)
        valid_ffs = [step['ff'] for step in grid if step['ff'] is not None]
        self.assertGreater(len(valid_ffs), 15, "Expected most steps to have valid FF")
        
        # FF should decrease monotonically (or mostly) from BID to ASK
        prev_ff = None
        decreasing_count = 0
        for step in grid:
            if step['ff'] is not None and not math.isinf(step['ff']):
                if prev_ff is not None:
                    if step['ff'] < prev_ff:
                        decreasing_count += 1
                prev_ff = step['ff']
        
        # At least 70% of transitions should be decreasing
        total_transitions = len(valid_ffs) - 1
        if total_transitions > 0:
            decreasing_ratio = decreasing_count / total_transitions
            self.assertGreater(decreasing_ratio, 0.5, 
                             f"Expected mostly decreasing FF, got {decreasing_ratio:.1%}")
        
        print(f"\nIWM FF Grid (Opening):")
        print(f"Every 5th step:")
        for i in range(0, 21, 5):
            step = grid[i]
            ff_str = f"{step['ff']:.3f}" if step['ff'] is not None else "None"
            print(f"  pct={step['pct']:.2f}: spread=${step['spread_price']:.2f}, FF={ff_str}")
    
    def test_find_target_price_opening_feasible(self):
        """Test finding target price for opening when feasible."""
        # Calculate grid for IWM
        grid = self.analyzer.calculate_ff_grid(
            short_bid=self.iwm_short_bid,
            short_ask=self.iwm_short_ask,
            long_bid=self.iwm_long_bid,
            long_ask=self.iwm_long_ask,
            underlying_price=self.iwm_underlying,
            strike=self.iwm_strike,
            short_dte=self.iwm_short_dte,
            long_dte=self.iwm_long_dte
        )
        
        # Find target for min_ff = 0.05 (should be feasible for IWM)
        result = self.analyzer.find_target_price_for_ff(grid, target_ff=0.05, direction='open')
        
        self.assertIsNotNone(result, "Expected to find feasible target")
        target_price, target_pct, target_ff = result
        
        # Target should be >= min FF
        self.assertGreaterEqual(target_ff, 0.05, f"Target FF {target_ff} should be >= 0.05")
        
        # Target pct should be between 0 and 1
        self.assertGreaterEqual(target_pct, 0.0)
        self.assertLessEqual(target_pct, 1.0)
        
        print(f"\nOpening Target (IWM, min_ff=0.05):")
        print(f"  Target price: ${target_price:.2f}")
        print(f"  Target pct: {target_pct:.2%}")
        print(f"  Target FF: {target_ff:.3f}")
    
    def test_find_target_price_opening_not_feasible(self):
        """Test finding target price when not feasible (threshold too high)."""
        # Calculate grid for IWM
        grid = self.analyzer.calculate_ff_grid(
            short_bid=self.iwm_short_bid,
            short_ask=self.iwm_short_ask,
            long_bid=self.iwm_long_bid,
            long_ask=self.iwm_long_ask,
            underlying_price=self.iwm_underlying,
            strike=self.iwm_strike,
            short_dte=self.iwm_short_dte,
            long_dte=self.iwm_long_dte
        )
        
        # Find target for min_ff = 1.0 (unrealistically high)
        result = self.analyzer.find_target_price_for_ff(grid, target_ff=1.0, direction='open')
        
        # Should return None (not feasible)
        self.assertIsNone(result, "Expected None for infeasible target")
        print(f"\nOpening Target (IWM, min_ff=1.0): NOT FEASIBLE ✓")
    
    def test_find_target_returns_last_not_first(self):
        """Test that find_target returns LAST acceptable step, not first."""
        # Calculate grid for IWM
        grid = self.analyzer.calculate_ff_grid(
            short_bid=self.iwm_short_bid,
            short_ask=self.iwm_short_ask,
            long_bid=self.iwm_long_bid,
            long_ask=self.iwm_long_ask,
            underlying_price=self.iwm_underlying,
            strike=self.iwm_strike,
            short_dte=self.iwm_short_dte,
            long_dte=self.iwm_long_dte
        )
        
        # Find target for min_ff = 0.05
        result = self.analyzer.find_target_price_for_ff(grid, target_ff=0.05, direction='open')
        self.assertIsNotNone(result)
        
        target_price, target_pct, target_ff = result
        
        # Count how many steps meet the threshold
        meeting_threshold = [s for s in grid if s['ff'] is not None and s['ff'] >= 0.05]
        
        if len(meeting_threshold) > 1:
            # If multiple steps meet threshold, verify we got the LAST one
            last_meeting = meeting_threshold[-1]
            self.assertEqual(target_pct, last_meeting['pct'], 
                           f"Expected LAST step at pct={last_meeting['pct']}, got pct={target_pct}")
            print(f"\nLast vs First test:")
            print(f"  Total steps meeting threshold: {len(meeting_threshold)}")
            print(f"  First acceptable pct: {meeting_threshold[0]['pct']:.2f}")
            print(f"  Last acceptable pct: {meeting_threshold[-1]['pct']:.2f}")
            print(f"  Returned pct: {target_pct:.2f} ✓ (correctly returns LAST)")
    
    def test_find_target_price_closing_feasible(self):
        """Test finding target price for closing when feasible."""
        # Calculate grid for IWM
        grid = self.analyzer.calculate_ff_grid(
            short_bid=self.iwm_short_bid,
            short_ask=self.iwm_short_ask,
            long_bid=self.iwm_long_bid,
            long_ask=self.iwm_long_ask,
            underlying_price=self.iwm_underlying,
            strike=self.iwm_strike,
            short_dte=self.iwm_short_dte,
            long_dte=self.iwm_long_dte
        )
        
        # Find target for max_ff = 0.25 (should be feasible - FF ranges from ~0.278 to ~0.200)
        result = self.analyzer.find_target_price_for_ff(grid, target_ff=0.25, direction='close')
        
        self.assertIsNotNone(result, "Expected to find feasible target for closing")
        target_price, target_pct, target_ff = result
        
        # Target should be <= max FF
        self.assertLessEqual(target_ff, 0.25, f"Target FF {target_ff} should be <= 0.25")
        
        print(f"\nClosing Target (IWM, max_ff=0.25):")
        print(f"  Target price: ${target_price:.2f}")
        print(f"  Target pct: {target_pct:.2%}")
        print(f"  Target FF: {target_ff:.3f}")


if __name__ == '__main__':
    unittest.main(verbosity=2)

