# Forward Factor Trading Implementation Plan

## Executive Summary

Add FF-based calendar spread trading using Black-Scholes IV estimation, forward volatility calculation, and solver-based price targeting.

**Commands**: `open_ff`, `close_ff`, enhanced `positions`  
**Algorithm**: Solve for target price where FF = threshold → walk from BID/ASK to target → fill anywhere in range  
**Feasibility**: If target price outside bid-ask spread, show error and exit (no execution)

---

## Core Logic

### Trading Algorithm

**Opening (Buying) - REVISED APPROACH**:
1. Get current market: short (bid/ask), long (bid/ask)
2. Calculate FF at BID execution: short@ask, long@bid
3. Calculate FF at ASK execution: short@bid, long@ask
4. **Discretize the spread**: Split into 20 steps (0% to 100%)
   - For each step `i` (0 to 20):
     - `pct = i / 20`
     - `short_price = short_ask - (short_ask - short_bid) * pct`  (moving from ASK toward BID)
     - `long_price = long_bid + (long_ask - long_bid) * pct`      (moving from BID toward ASK)
     - Calculate IVs from these prices
     - Calculate FF from IVs
     - Calculate spread_price = long_price - short_price
5. **Find target**: **LAST** step where FF >= min_ff (closest to ASK while still meeting threshold)
   - FF is HIGHEST at BID, DECREASES toward ASK
   - We want to capture ALL good prices from BID to the furthest acceptable point
   - Example: If steps 0-12 have FF >= 0.20, target is step 12
6. **Walk**: Start at spread BID, walk UP through all good prices to target spread price
7. **Stop**: When filled OR reached target price

**Closing (Selling) - REVISED APPROACH**:
1. Get current market: short (bid/ask), long (bid/ask)  
2. Calculate FF at ASK execution: short@ask, long@bid (what we'll get)
3. Calculate FF at BID execution: short@bid, long@ask (worst we'll get)
4. **Discretize the spread**: Split into 20 steps (0% to 100%)
   - For each step `i` (0 to 20):
     - `pct = i / 20`
     - `short_price = short_bid + (short_ask - short_bid) * pct`  (moving from BID toward ASK)
     - `long_price = long_ask - (long_ask - long_bid) * pct`      (moving from ASK toward BID)
     - Calculate IVs from these prices
     - Calculate FF from IVs
     - Calculate spread_price = long_price - short_price
5. **Find target**: **LAST** step where FF <= max_ff (closest to BID while still meeting threshold)
   - FF is LOWEST at ASK, INCREASES toward BID
   - We want to capture ALL good prices from ASK down to the furthest acceptable point
   - Example: If steps 0-8 have FF <= 0.0, target is step 8
6. **Walk**: Start at spread ASK, walk DOWN through all good prices to target spread price
7. **Stop**: When filled OR reached target price

**Feasibility Check**:
- If min_ff/max_ff threshold is beyond the opposite end of spread, show "NOT FEASIBLE"
- Display the FF range (BID to ASK) and suggest adjusted threshold

### IV Calculation Rules
- **Positions display**: Use MID price for both legs
- **Trading (Opening)**: 
  - BID execution: short@ask, long@bid
  - Intermediate steps: Interpolate linearly between BID and ASK execution
  - ASK execution: short@bid, long@ask
- **Trading (Closing)**: 
  - ASK execution: short@ask, long@bid (starting point)
  - Intermediate steps: Interpolate linearly between ASK and BID execution
  - BID execution: short@bid, long@ask (ending point)

### FF Discretization Grid
- **20 steps** from 0% to 100% through the bid-ask spread
- **Actual execution prices** used at each step (not decomposed from spread price)
- **Monotonic FF**: FF should **DECREASE** as spread cost increases (from BID to ASK when opening)
- **Target finding**: 
  - **Opening**: Find LAST step where FF >= min_ff (walk BID → Target, capturing all good prices)
  - **Closing**: Find LAST step where FF <= max_ff (walk ASK → Target, capturing all good prices)

---

## Implementation Files

### New Files
1. **`utils/black_scholes.py`**
   - `black_scholes_call()` - BSM pricing
   - `estimate_iv_from_price()` - Newton-Raphson IV solver (tolerance=1e-5)
   - `vega()` - For convergence

2. **`utils/forward_factor.py`**
   - `calculate_forward_variance()` - (σ₂²·T₂ − σ₁²·T₁) / (T₂ − T₁)
   - `calculate_forward_vol()` - √(ForwardVariance)
   - `calculate_forward_factor()` - (Front IV − Forward Vol) / Forward Vol

3. **`utils/risk_free_rate.py`**
   - Return 4.5% hardcoded (add API fetch later)

4. **`forward_factor_analyzer.py`**
   - `analyze_calendar_spread_for_reporting()` - For positions display (uses MID prices)
   - **`calculate_ff_grid(short_bid, short_ask, long_bid, long_ask, underlying_price, strike, short_dte, long_dte)`**
     - Returns list of 20 dicts: `[{'pct': 0.0, 'spread_price': X, 'ff': Y, 'short_price': A, 'long_price': B}, ...]`
     - For opening: pct=0 is BID execution, pct=1.0 is ASK execution
     - For closing: reverse the interpretation
   - **`find_target_price_for_ff(ff_grid, target_ff, direction='open')`**
     - For opening: Find LAST step where FF >= target_ff (furthest acceptable price from BID)
     - For closing: Find LAST step where FF <= target_ff (furthest acceptable price from ASK)
     - Returns target spread price or None if not feasible
   - `get_calendar_spreads_with_ff()` - Find calendars in positions

### Modified Files
1. **`shell.py`**
   - `do_open_ff()` - Open calendar at min_ff threshold
   - `do_close_ff()` - Close calendar at max_ff threshold
   - `do_positions()` - Show FF for existing calendars (cached 30s, `--no-ff` to skip)

2. **`walk_limit_engine.py`**
   - `start_open_ff_process()` - Returns process_id or None (not feasible)
     - Calculates FF grid (20 steps)
     - Finds target price: LAST step where FF >= min_ff
     - Walk captures ALL prices from BID to target (all good FF values)
     - If feasible: Starts walk from BID to target
     - If not feasible: Returns None with error message
   - `start_close_ff_process()` - Returns process_id or None (not feasible)
     - Calculates FF grid (20 steps)
     - Finds target price: LAST step where FF <= max_ff
     - Walk captures ALL prices from ASK to target (all good FF values)
     - If feasible: Starts walk from ASK to target
     - If not feasible: Returns None with error message
   - Add fields to `WalkLimitProcess`: `is_ff_strategy`, `ff_threshold`, `ff_target_price`, `ff_grid`

3. **`confirmation_card.py`**
   - `display_ff_confirmation()` - Show:
     - Current market (short bid/ask, long bid/ask, underlying price)
     - **FF Grid Summary**:
       - FF at BID execution (best case)
       - FF at MID execution (expected)
       - FF at ASK execution (worst case)
     - Target threshold and calculated target price
     - **Walk Strategy**:
       - Starting price (BID for open, ASK for close)
       - Target price (where FF meets threshold)
       - FF range achievable in walk
     - **✅ FEASIBLE** (show walk range) or **❌ NOT FEASIBLE** (show FF range, suggest adjusted threshold)
     - Risk metrics (max debit, Greeks)

4. **`position_analyzer.py`**
   - Calculate FF for existing calendar spreads using MID prices

5. **`config.py`**
   ```python
   FF_MIN_THRESHOLD_DEFAULT = 0.2
   FF_MAX_THRESHOLD_DEFAULT = 0.0
   FF_RISK_FREE_RATE = 0.045
   ```

6. **`requirements.txt`**
   - Add `scipy>=1.11.0`, `numpy>=1.24.0`

---

## Commands

### `open_ff` - Open Calendar at Min FF
```bash
open_ff <symbol> <short_exp> <long_exp> <strike> <qty> [--min_ff=0.2] [--max_wait_time=42] [--execute]
```
Example: `open_ff AAPL 2025-11-21 2025-12-19 170 5 --min_ff=0.25 --execute`

### `close_ff` - Close Calendar at Max FF
```bash
close_ff <symbol> <short_exp> <long_exp> <strike> <qty> [--max_ff=0.0] [--max_wait_time=42] [--execute]
```
Example: `close_ff AAPL 2025-11-21 2025-12-19 170 5 --max_ff=0 --execute`

### `positions` - Show FF for Calendars
Color coding:
- Green (FF > 0.2): "✅ BACKWARDATION"
- Yellow (0 < FF < 0.2): "⚡ SLIGHT BACKWARDATION"  
- Red (FF < 0): "⚠️ MEAN REVERTED"

---

## Implementation Phases (6 weeks)

**Phase 1 (Week 1)**: Foundation - Create BSM, FF calculator, risk-free rate modules + tests  
**Phase 2 (Week 2)**: Analysis Layer - Create ForwardFactorAnalyzer with solver + tests  
**Phase 3 (Week 3)**: UI - Add FF confirmation card with feasibility check  
**Phase 4 (Week 4)**: Walk Engine - Add FF-aware processes with target price logic  
**Phase 5 (Week 5)**: Shell Commands - Implement open_ff, close_ff, enhance positions  
**Phase 6 (Week 6)**: Testing - End-to-end, edge cases, paper trading validation

---

## Key Design Decisions

1. **Grid-based FF calculation**: Discretize bid-ask spread into 20 steps, calculate FF at each
   - More accurate than solver - uses actual execution prices
   - Transparent - can display full FF curve
   - Avoids decomposition issues from spread price
2. **Linear interpolation**: Move both leg prices proportionally through bid-ask range
3. **One-time calculation**: Calculate FF grid once, find target, walk to it, stop
4. **Feasibility check**: If threshold not achievable in bid-ask range, show "NOT FEASIBLE"
5. **No walking if unfeasible**: If target outside bid-ask, cannot execute
6. **MID for reporting**: Positions display uses MID prices for IV/FF calculation
7. **ATF drift**: Use market-implied forward rates instead of static risk-free rate

```
scipy>=1.11.0  # For norm.cdf() in BSM and optimize.brentq() for solving
numpy>=1.24.0  # For numerical calculations
```

---

## Success Criteria

1. ✅ User can run `open_ff` and `close_ff` commands
2. ✅ FF calculated correctly vs manual calculation
3. ✅ IV estimation within 1% of market IV
4. ✅ Walk stops at FF threshold price
5. ✅ Positions display shows FF for calendars
6. ✅ All cancellation mechanisms work
7. ✅ Comprehensive testing complete
