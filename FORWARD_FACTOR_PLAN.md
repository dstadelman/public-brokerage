# Forward Factor Trading Implementation Plan

## Executive Summary

Add FF-based calendar spread trading using Black-Scholes IV estimation, forward volatility calculation, and solver-based price targeting.

**Commands**: `open_ff`, `close_ff`, enhanced `positions`  
**Algorithm**: Solve for target price where FF = threshold → walk from BID/ASK to target → fill anywhere in range  
**Feasibility**: If target price outside bid-ask spread, show error and exit (no execution)

---

## Core Logic

### Trading Algorithm

**Opening (Buying)**:
1. Solve: `max_acceptable_price` where FF = min_ff (e.g., $1.20 @ FF=0.20)
2. Get current BID
3. If `max_acceptable_price >= BID`: Walk BID → max_acceptable_price ✅
4. Else: Show "NOT FEASIBLE", exit ❌

**Closing (Selling)**:
1. Solve: `min_acceptable_price` where FF = max_ff (e.g., $0.50 @ FF=0.0)
2. Get current ASK  
3. If `min_acceptable_price <= ASK`: Walk ASK → min_acceptable_price ✅
4. Else: Show "NOT FEASIBLE", exit ❌

### IV Calculation Rules
- **Positions display**: Use MID price
- **Trading**: Solve for target price from FF threshold

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
   - `analyze_calendar_spread_for_reporting()` - For positions display
   - `calculate_ff_at_spread_price(spread_price)` - Map price → FF
   - `solve_for_spread_price_at_ff(target_ff)` - Solve using scipy.optimize.brentq
   - `get_calendar_spreads_with_ff()` - Find calendars in positions

### Modified Files
1. **`shell.py`**
   - `do_open_ff()` - Open calendar at min_ff threshold
   - `do_close_ff()` - Close calendar at max_ff threshold
   - `do_positions()` - Show FF for existing calendars (cached 30s, `--no-ff` to skip)

2. **`walk_limit_engine.py`**
   - `start_open_ff_process()` - Returns process_id or None (not feasible)
   - `start_close_ff_process()` - Returns process_id or None (not feasible)
   - Add fields to `WalkLimitProcess`: `is_ff_strategy`, `ff_threshold`, `ff_target_price`

3. **`confirmation_card.py`**
   - `display_ff_confirmation()` - Show:
     - Current market (BID/ASK/MID, underlying price)
     - FF analysis (front IV, back IV, forward vol, current FF)
     - Target threshold and solved price
     - **✅ FEASIBLE** (show walk range) or **❌ NOT FEASIBLE** (show suggestions, exit)
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

1. **Solver-based**: Use scipy.optimize.brentq to find exact price where FF = threshold
2. **One-time calculation**: Calculate target price once, walk to it, stop
3. **Feasibility check**: Show before execution, auto-exit if not feasible
4. **No walking if unfeasible**: If target outside bid-ask, cannot execute
5. **MID for reporting**: Positions display uses MID prices for IV/FF calculation
6. **Risk-free rate**: Hardcoded 4.5% initially

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
