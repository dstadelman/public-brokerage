"""
Unit tests for forward volatility and forward factor calculations.
"""

import unittest
import math
from utils.forward_factor import (
    calculate_forward_variance,
    calculate_forward_vol,
    calculate_forward_factor,
    calculate_forward_factor_from_ivs
)


class TestForwardVariance(unittest.TestCase):
    """Test forward variance calculation."""
    
    def test_forward_variance_backwardation(self):
        """Test forward variance with front IV > back IV (backwardation)."""
        # Front: 45% IV, 10 DTE
        # Back: 38% IV, 38 DTE
        forward_var = calculate_forward_variance(
            front_iv=0.45, front_dte=10,
            back_iv=0.38, back_dte=38
        )
        
        self.assertIsNotNone(forward_var)
        self.assertGreater(forward_var, 0.0)
    
    def test_forward_variance_contango(self):
        """Test forward variance with front IV < back IV (contango)."""
        # Front: 30% IV, 10 DTE
        # Back: 40% IV, 38 DTE
        forward_var = calculate_forward_variance(
            front_iv=0.30, front_dte=10,
            back_iv=0.40, back_dte=38
        )
        
        self.assertIsNotNone(forward_var)
        self.assertGreater(forward_var, 0.0)
    
    def test_forward_variance_invalid_dte(self):
        """Test forward variance fails when front DTE >= back DTE."""
        # Front expires same time or after back (invalid)
        forward_var = calculate_forward_variance(
            front_iv=0.40, front_dte=40,
            back_iv=0.38, back_dte=38
        )
        
        self.assertIsNone(forward_var)
    
    def test_forward_variance_negative_dte(self):
        """Test forward variance fails with negative DTE."""
        forward_var = calculate_forward_variance(
            front_iv=0.40, front_dte=-5,
            back_iv=0.38, back_dte=38
        )
        
        self.assertIsNone(forward_var)
    
    def test_forward_variance_negative_iv(self):
        """Test forward variance fails with negative IV."""
        forward_var = calculate_forward_variance(
            front_iv=-0.40, front_dte=10,
            back_iv=0.38, back_dte=38
        )
        
        self.assertIsNone(forward_var)


class TestForwardVol(unittest.TestCase):
    """Test forward volatility calculation."""
    
    def test_forward_vol_typical_calendar(self):
        """Test forward vol for typical calendar spread."""
        # Front: 45% IV, 10 DTE
        # Back: 38% IV, 38 DTE
        forward_vol = calculate_forward_vol(
            front_iv=0.45, front_dte=10,
            back_iv=0.38, back_dte=38
        )
        
        self.assertIsNotNone(forward_vol)
        self.assertGreater(forward_vol, 0.0)
        # Forward vol should be between front and back
        self.assertGreater(forward_vol, 0.20)
        self.assertLess(forward_vol, 0.60)
    
    def test_forward_vol_known_values(self):
        """Test forward vol with manually calculated values."""
        # Simple case: Front 40% 30 DTE, Back 30% 60 DTE
        # T1 = 30/365, T2 = 60/365
        # ForwardVar = (0.30² * 60/365 - 0.40² * 30/365) / (30/365)
        # ForwardVar = (0.09 * 0.164 - 0.16 * 0.082) / 0.082
        # ForwardVar = (0.01476 - 0.01312) / 0.082 = 0.00164 / 0.082 = 0.02
        # ForwardVol = sqrt(0.02) = 0.1414...
        
        forward_vol = calculate_forward_vol(
            front_iv=0.40, front_dte=30,
            back_iv=0.30, back_dte=60
        )
        
        self.assertIsNotNone(forward_vol)
        # Allow some rounding tolerance
        self.assertAlmostEqual(forward_vol, 0.1414, delta=0.01)


class TestForwardFactor(unittest.TestCase):
    """Test forward factor calculation."""
    
    def test_forward_factor_backwardation(self):
        """Test FF > 0 when front IV > forward vol (backwardation)."""
        # Front IV = 45%, Forward Vol = 35%
        ff = calculate_forward_factor(front_iv=0.45, forward_vol=0.35)
        
        self.assertIsNotNone(ff)
        # FF = (0.45 - 0.35) / 0.35 = 0.10 / 0.35 = 0.2857
        self.assertAlmostEqual(ff, 0.2857, delta=0.01)
        self.assertGreater(ff, 0.0)
    
    def test_forward_factor_flat(self):
        """Test FF = 0 when front IV = forward vol."""
        ff = calculate_forward_factor(front_iv=0.40, forward_vol=0.40)
        
        self.assertIsNotNone(ff)
        self.assertAlmostEqual(ff, 0.0, delta=0.001)
    
    def test_forward_factor_contango(self):
        """Test FF < 0 when front IV < forward vol (contango/mean reversion)."""
        # Front IV = 30%, Forward Vol = 40%
        ff = calculate_forward_factor(front_iv=0.30, forward_vol=0.40)
        
        self.assertIsNotNone(ff)
        # FF = (0.30 - 0.40) / 0.40 = -0.10 / 0.40 = -0.25
        self.assertAlmostEqual(ff, -0.25, delta=0.01)
        self.assertLess(ff, 0.0)
    
    def test_forward_factor_zero_forward_vol(self):
        """Test FF fails with zero forward vol."""
        ff = calculate_forward_factor(front_iv=0.40, forward_vol=0.0)
        self.assertIsNone(ff)
    
    def test_forward_factor_negative_iv(self):
        """Test FF fails with negative IV."""
        ff = calculate_forward_factor(front_iv=-0.40, forward_vol=0.35)
        self.assertIsNone(ff)


class TestForwardFactorFromIVs(unittest.TestCase):
    """Test convenience function for calculating FF from IVs."""
    
    def test_ff_from_ivs_backwardation(self):
        """Test FF calculation directly from front/back IVs."""
        # Front: 45% IV, 10 DTE
        # Back: 38% IV, 38 DTE
        # Should give positive FF (backwardation)
        ff = calculate_forward_factor_from_ivs(
            front_iv=0.45, front_dte=10,
            back_iv=0.38, back_dte=38
        )
        
        self.assertIsNotNone(ff)
        self.assertGreater(ff, 0.0)
    
    def test_ff_from_ivs_contango(self):
        """Test FF with mean reversion (contango)."""
        # Front: 30% IV, 10 DTE
        # Back: 40% IV, 38 DTE
        # Should give negative FF (mean reversion)
        ff = calculate_forward_factor_from_ivs(
            front_iv=0.30, front_dte=10,
            back_iv=0.40, back_dte=38
        )
        
        self.assertIsNotNone(ff)
        self.assertLess(ff, 0.0)
    
    def test_ff_from_ivs_invalid_dates(self):
        """Test FF fails with invalid expiration dates."""
        ff = calculate_forward_factor_from_ivs(
            front_iv=0.45, front_dte=40,
            back_iv=0.38, back_dte=38
        )
        
        self.assertIsNone(ff)


if __name__ == '__main__':
    unittest.main()
