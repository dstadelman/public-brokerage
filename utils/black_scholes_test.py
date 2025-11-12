"""
Unit tests for Black-Scholes-Merton option pricing and IV estimation.
"""

import unittest
import math
from utils.black_scholes import black_scholes_call, vega, estimate_iv_from_price


class TestBlackScholes(unittest.TestCase):
    """Test Black-Scholes-Merton pricing functions."""
    
    def test_black_scholes_call_atm(self):
        """Test BSM pricing for at-the-money call."""
        # S=K=100, T=1 year, r=5%, sigma=20%, q=0
        price = black_scholes_call(S=100, K=100, T=1.0, r=0.05, sigma=0.20, q=0.0)
        
        # Expected: ~10.45 (verified with external calculator)
        self.assertAlmostEqual(price, 10.45, delta=0.1)
    
    def test_black_scholes_call_itm(self):
        """Test BSM pricing for in-the-money call."""
        # S=110, K=100, T=1 year, r=5%, sigma=20%, q=0
        price = black_scholes_call(S=110, K=100, T=1.0, r=0.05, sigma=0.20, q=0.0)
        
        # Should be > intrinsic value of 10
        self.assertGreater(price, 10.0)
        self.assertLess(price, 20.0)
    
    def test_black_scholes_call_otm(self):
        """Test BSM pricing for out-of-the-money call."""
        # S=90, K=100, T=1 year, r=5%, sigma=20%, q=0
        price = black_scholes_call(S=90, K=100, T=1.0, r=0.05, sigma=0.20, q=0.0)
        
        # Should be > 0 but < 10
        self.assertGreater(price, 0.0)
        self.assertLess(price, 10.0)
    
    def test_black_scholes_call_zero_time(self):
        """Test BSM pricing at expiration (T=0)."""
        # S=110, K=100, T=0, should return intrinsic value
        price = black_scholes_call(S=110, K=100, T=0.0, r=0.05, sigma=0.20, q=0.0)
        self.assertEqual(price, 10.0)
        
        # OTM at expiration should be 0
        price = black_scholes_call(S=90, K=100, T=0.0, r=0.05, sigma=0.20, q=0.0)
        self.assertEqual(price, 0.0)
    
    def test_black_scholes_call_zero_vol(self):
        """Test BSM pricing with zero volatility."""
        # S=110, K=100, T=1, sigma=0 (ITM)
        price = black_scholes_call(S=110, K=100, T=1.0, r=0.05, sigma=0.0, q=0.0)
        
        # Should be discounted intrinsic value
        expected = 110 - 100 * math.exp(-0.05 * 1.0)
        self.assertAlmostEqual(price, expected, delta=0.01)
    
    def test_vega_calculation(self):
        """Test vega calculation."""
        # S=K=100, T=1 year, r=5%, sigma=20%
        v = vega(S=100, K=100, T=1.0, r=0.05, sigma=0.20, q=0.0)
        
        # Vega should be positive for ATM options
        self.assertGreater(v, 0.0)
        # Typical vega for ATM option ~40
        self.assertAlmostEqual(v, 40.0, delta=5.0)
    
    def test_vega_zero_time(self):
        """Test vega at expiration."""
        v = vega(S=100, K=100, T=0.0, r=0.05, sigma=0.20, q=0.0)
        self.assertEqual(v, 0.0)


class TestImpliedVolatility(unittest.TestCase):
    """Test implied volatility estimation."""
    
    def test_iv_estimation_atm(self):
        """Test IV estimation for ATM option."""
        # Known: S=K=100, T=1, r=5%, sigma=20% -> price ~10.45
        true_sigma = 0.20
        price = black_scholes_call(S=100, K=100, T=1.0, r=0.05, sigma=true_sigma, q=0.0)
        
        # Estimate IV from price
        estimated_iv = estimate_iv_from_price(
            option_price=price,
            S=100, K=100, T=1.0, r=0.05, q=0.0
        )
        
        self.assertIsNotNone(estimated_iv)
        self.assertAlmostEqual(estimated_iv, true_sigma, delta=0.001)
    
    def test_iv_estimation_itm(self):
        """Test IV estimation for ITM option."""
        true_sigma = 0.30
        price = black_scholes_call(S=110, K=100, T=0.5, r=0.05, sigma=true_sigma, q=0.0)
        
        estimated_iv = estimate_iv_from_price(
            option_price=price,
            S=110, K=100, T=0.5, r=0.05, q=0.0
        )
        
        self.assertIsNotNone(estimated_iv)
        self.assertAlmostEqual(estimated_iv, true_sigma, delta=0.001)
    
    def test_iv_estimation_otm(self):
        """Test IV estimation for OTM option."""
        true_sigma = 0.40
        price = black_scholes_call(S=90, K=100, T=0.25, r=0.05, sigma=true_sigma, q=0.0)
        
        estimated_iv = estimate_iv_from_price(
            option_price=price,
            S=90, K=100, T=0.25, r=0.05, q=0.0
        )
        
        self.assertIsNotNone(estimated_iv)
        self.assertAlmostEqual(estimated_iv, true_sigma, delta=0.001)
    
    def test_iv_below_intrinsic_value(self):
        """Test IV estimation fails for price below intrinsic value."""
        # S=110, K=100, intrinsic = 10
        # Try to estimate IV for price = 5 (below intrinsic)
        estimated_iv = estimate_iv_from_price(
            option_price=5.0,
            S=110, K=100, T=0.5, r=0.05, q=0.0
        )
        
        # Should return None (arbitrage violation)
        self.assertIsNone(estimated_iv)
    
    def test_iv_zero_price(self):
        """Test IV estimation fails for zero price."""
        estimated_iv = estimate_iv_from_price(
            option_price=0.0,
            S=100, K=100, T=1.0, r=0.05, q=0.0
        )
        
        self.assertIsNone(estimated_iv)
    
    def test_iv_zero_time(self):
        """Test IV estimation fails at expiration."""
        estimated_iv = estimate_iv_from_price(
            option_price=10.0,
            S=110, K=100, T=0.0, r=0.05, q=0.0
        )
        
        self.assertIsNone(estimated_iv)
    
    def test_iv_convergence_high_vol(self):
        """Test IV estimation converges for high volatility."""
        true_sigma = 1.0  # 100% volatility
        price = black_scholes_call(S=100, K=100, T=1.0, r=0.05, sigma=true_sigma, q=0.0)
        
        estimated_iv = estimate_iv_from_price(
            option_price=price,
            S=100, K=100, T=1.0, r=0.05, q=0.0
        )
        
        self.assertIsNotNone(estimated_iv)
        self.assertAlmostEqual(estimated_iv, true_sigma, delta=0.01)
    
    def test_iv_convergence_low_vol(self):
        """Test IV estimation converges for low volatility."""
        true_sigma = 0.05  # 5% volatility
        price = black_scholes_call(S=100, K=100, T=1.0, r=0.05, sigma=true_sigma, q=0.0)
        
        estimated_iv = estimate_iv_from_price(
            option_price=price,
            S=100, K=100, T=1.0, r=0.05, q=0.0
        )
        
        self.assertIsNotNone(estimated_iv)
        self.assertAlmostEqual(estimated_iv, true_sigma, delta=0.001)


if __name__ == '__main__':
    unittest.main()
