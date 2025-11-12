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


if __name__ == '__main__':
    unittest.main(verbosity=2)
