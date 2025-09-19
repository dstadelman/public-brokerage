# Requirements

This project implements a sophisticated options trading system with walk limit order execution. The system provides:

## Current Features
- **Call Spread Trading**: Open and close call spreads with walk limit orders
- **Position Analysis**: Analyze existing positions and identify spread opportunities
- **Walk Limit Engine**: Incrementally walk order prices to improve fill rates
- **Confirmation Cards**: Display detailed trade confirmations with risk analysis
- **Portfolio Management**: View positions, P&L, and portfolio analytics

## New Feature Requirements

### Single Leg Option Trading
We need to add support for single-leg option trading to complement the existing spread trading functionality:

#### `open_position` Command
- **Purpose**: Open individual option positions (calls or puts)
- **Syntax**: `open_position <ticker> <expiration> <type> <strike> <quantity> [--max_wait_time=42] [--execute]`
- **Parameters**:
  - `ticker`: Underlying symbol (e.g., AAPL, SPY)
  - `expiration`: Option expiration date (YYYY-MM-DD format)
  - `type`: Option type (C for call, P for put)
  - `strike`: Strike price (float)
  - `quantity`: Number of contracts (positive = buy, negative = sell)
  - `--max_wait_time`: Maximum time to wait per price level (default: 42 seconds)
  - `--execute`: Execute actual orders (default: dry run)

#### `close_position` Command
- **Purpose**: Close existing option positions using walk limit orders
- **Syntax**: `close_position <ticker> <expiration> <type> <strike> <quantity> [--max_wait_time=42] [--execute]`
- **Parameters**: Same as `open_position`
- **Safety**: Must verify position exists in portfolio before allowing order

### Design Goals
- **Consistent UX**: Follow same patterns as existing spread commands
- **Walk Limit Orders**: Use same incremental pricing strategy for better fills
- **Risk Management**: Include all existing safety checks and confirmations
- **Portfolio Integration**: Verify positions before closing trades
- **Comprehensive Logging**: Detailed execution logging like existing features

---

# TASKS

## Phase 1: Core Infrastructure for Single-Leg Options

### Task 1.1: Extend WalkLimitEngine for Single-Leg Support
**File**: `walk_limit_engine.py`
**Priority**: High

- [ ] Add `WalkLimitProcess` support for single-leg strategies
  - [ ] Add strategy types: `'open_single_leg'`, `'close_single_leg'`
  - [ ] Modify process dataclass to handle single option symbol instead of spread symbols
- [ ] Implement `start_open_single_leg_process()` method
  - [ ] Take parameters: symbol, expiration, option_type, strike, quantity, account_id, max_wait_time, execute_mode
  - [ ] Construct OSI option symbol using existing utility functions
  - [ ] Get current option pricing (with fallback to option chain like existing code)
  - [ ] Calculate walk pricing based on bid/ask spread
  - [ ] Initialize and start background process
- [ ] Implement `start_close_single_leg_process()` method
  - [ ] Similar to open but verify position exists first
  - [ ] Use `get_account_portfolio()` to check current positions
  - [ ] Validate requested close quantity doesn't exceed position size
- [ ] Add `_run_single_leg_process()` method
  - [ ] Similar to existing `_run_open_spread_process()` but for single legs
  - [ ] Use `preflight_single_leg()` instead of `preflight_multi_leg()`
  - [ ] Handle BUY/SELL sides based on positive/negative quantity
  - [ ] Set correct `OpenCloseIndicator` (OPEN vs CLOSE)

### Task 1.2: Add Single-Leg Confirmation Cards
**File**: `confirmation_card.py`
**Priority**: High

- [ ] Implement `display_single_leg_confirmation()` method
  - [ ] Show option details (symbol, strike, expiration, type)
  - [ ] Display current bid/ask/last pricing
  - [ ] Show quantity and side (BUY/SELL, OPEN/CLOSE)
  - [ ] Calculate estimated costs and commissions
  - [ ] Display option Greeks (delta, gamma, theta, vega)
  - [ ] Show risk metrics and breakeven analysis
  - [ ] Include execution details (dry run vs live, max wait time)
- [ ] Add helper methods for single-leg analysis
  - [ ] `_get_single_option_greeks()` - retrieve Greeks for option
  - [ ] `_calculate_single_leg_risk()` - calculate max profit/loss
  - [ ] `_format_single_leg_display()` - format confirmation display

### Task 1.3: Position Validation for Close Orders
**File**: `position_analyzer.py` (new methods)
**Priority**: High

- [ ] Add `find_option_position()` method
  - [ ] Search portfolio for specific option by symbol
  - [ ] Return position details if found
- [ ] Add `validate_close_quantity()` method
  - [ ] Verify requested close quantity doesn't exceed position
  - [ ] Handle partial closes appropriately
- [ ] Extend existing position analysis for single legs
  - [ ] Add single-leg position identification
  - [ ] Include in portfolio summary displays

## Phase 2: Shell Command Implementation

### Task 2.1: Add open_position Command
**File**: `shell.py`
**Priority**: High

- [ ] Implement `do_open_position()` method
  - [ ] Parse command line arguments using argparse
  - [ ] Validate parameters (ticker, expiration date format, option type, strike, quantity)
  - [ ] Check default account is set
  - [ ] Call confirmation card for user approval
  - [ ] Start walk limit process via engine
  - [ ] Display process ID and monitoring instructions
- [ ] Add command to help system
- [ ] Add usage examples to help text

### Task 2.2: Add close_position Command  
**File**: `shell.py`
**Priority**: High

- [ ] Implement `do_close_position()` method
  - [ ] Similar to open_position but with position validation
  - [ ] Check that position exists before allowing close
  - [ ] Validate close quantity against position size
  - [ ] Call appropriate confirmation card
  - [ ] Start close process via engine
- [ ] Add error handling for position not found
- [ ] Add command to help system

## Phase 3: API Integration and Order Management

### Task 3.1: Single-Leg Order Execution
**Files**: `public_brokerage/orders.py`, models
**Priority**: Medium

- [ ] Verify `preflight_single_leg()` handles all option scenarios
  - [ ] Test with BUY/SELL for both calls and puts
  - [ ] Verify OPEN/CLOSE indicators work correctly
  - [ ] Test with various strike prices and expirations
- [ ] Ensure `place_single_leg_order()` supports all parameters
  - [ ] OrderSide: BUY/SELL based on quantity sign
  - [ ] OpenCloseIndicator: OPEN for new positions, CLOSE for exits
  - [ ] Proper error handling and validation
- [ ] Add any missing model fields for single-leg support

### Task 3.2: Order Monitoring and Status
**File**: `walk_limit_engine.py`
**Priority**: Medium

- [ ] Extend status reporting for single-leg processes
  - [ ] Show single option symbol instead of spread symbols
  - [ ] Display appropriate progress metrics
  - [ ] Handle partial fills correctly
- [ ] Update process cancellation logic
  - [ ] Ensure single-leg orders can be cancelled properly
  - [ ] Clean up process state correctly

## Phase 4: Manual Testing and Validation

### Task 4.1: Manual Testing with Real Market Data
**Files**: Manual testing scripts and documentation
**Priority**: Medium

- [ ] **Phase 1: Dry-Run Testing (No --execute flag)**
  - [ ] Test buying calls: `open_position AAPL 2024-02-16 C 145.00 1`
  - [ ] Test buying puts: `open_position AAPL 2024-02-16 P 145.00 1`
  - [ ] Test selling calls: `open_position AAPL 2024-02-16 C 145.00 -1`
  - [ ] Test selling puts: `open_position AAPL 2024-02-16 P 145.00 -1`
  - [ ] Verify pricing calculations match option chain data
  - [ ] Test walk limit order progression simulation
  - [ ] Validate all confirmation cards display correctly
  - [ ] Test position validation logic without actual orders
- [ ] **Phase 2: Live Testing (With --execute flag)**
  - [ ] Start with small quantities and liquid options
  - [ ] Test buying calls: `open_position AAPL 2024-02-16 C 145.00 1 --execute`
  - [ ] Test buying puts: `open_position AAPL 2024-02-16 P 145.00 1 --execute`
  - [ ] Test selling calls: `open_position AAPL 2024-02-16 C 145.00 -1 --execute`
  - [ ] Test selling puts: `open_position AAPL 2024-02-16 P 145.00 -1 --execute`
  - [ ] Verify actual orders are placed and filled correctly
  - [ ] Test real walk limit order progression with market data
- [ ] Test `close_position` command safety features
  - [ ] **Dry-run first**: `close_position AAPL 2024-02-16 C 145.00 1`
  - [ ] Verify position validation works correctly
  - [ ] Test error handling when position doesn't exist
  - [ ] Test quantity validation (can't close more than you own)
  - [ ] **Live testing**: `close_position AAPL 2024-02-16 C 145.00 1 --execute`
  - [ ] Test partial position closes with real portfolio
- [ ] Test edge cases and error scenarios
  - [ ] Invalid expiration dates
  - [ ] Non-existent strikes
  - [ ] Market closed scenarios
  - [ ] Network connectivity issues

### Task 4.2: API Integration Testing
**Files**: Test against real Public Brokerage API
**Priority**: Medium

- [ ] Test single-leg option API workflows
  - [ ] **Get Option Expirations**:
    ```bash
    curl --request POST \
      --url https://api.public.com/userapigateway/marketdata/{ACCOUNT_ID}/option-expirations \
      --header 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
      --header 'Content-Type: application/json' \
      --data '{"instrument": {"symbol": "AAPL", "type": "EQUITY"}}'
    ```
  - [ ] **Get Option Chain**:
    ```bash
    curl --request POST \
      --url https://api.public.com/userapigateway/marketdata/{ACCOUNT_ID}/option-chain \
      --header 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
      --header 'Content-Type: application/json' \
      --data '{"instrument": {"symbol": "AAPL", "type": "EQUITY"}, "expirationDate": "2024-02-16"}'
    ```
  - [ ] **Get Option Quotes**:
    ```bash
    curl --request POST \
      --url https://api.public.com/userapigateway/marketdata/{ACCOUNT_ID}/quotes \
      --header 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
      --header 'Content-Type: application/json' \
      --data '{"instruments": [{"symbol": "AAPL240216C00145000", "type": "OPTION"}]}'
    ```
  - [ ] **Preflight Single-Leg Order**:
    ```bash
    curl --request POST \
      --url https://api.public.com/userapigateway/trading/{ACCOUNT_ID}/preflight/single-leg \
      --header 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
      --header 'Content-Type: application/json' \
      --data '{
        "instrument": {"symbol": "AAPL240216C00145000", "type": "OPTION"},
        "orderSide": "BUY",
        "orderType": "LIMIT",
        "expiration": {"timeInForce": "DAY"},
        "quantity": "1",
        "limitPrice": "7.50",
        "openCloseIndicator": "OPEN"
      }'
    ```
  - [ ] **Place Single-Leg Order**:
    ```bash
    curl --request POST \
      --url https://api.public.com/userapigateway/trading/{ACCOUNT_ID}/order \
      --header 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
      --header 'Content-Type: application/json' \
      --data '{
        "orderId": "550e8400-e29b-41d4-a716-446655440001",
        "instrument": {"symbol": "AAPL240216C00145000", "type": "OPTION"},
        "orderSide": "BUY",
        "orderType": "LIMIT",
        "expiration": {"timeInForce": "DAY"},
        "quantity": "1",
        "limitPrice": "7.50",
        "openCloseIndicator": "OPEN"
      }'
    ```
  - [ ] **Check Order Status**:
    ```bash
    curl --request GET \
      --url https://api.public.com/userapigateway/trading/{ACCOUNT_ID}/order/550e8400-e29b-41d4-a716-446655440001 \
      --header 'Authorization: Bearer YOUR_ACCESS_TOKEN'
    ```
  - [ ] **Get Portfolio Positions**:
    ```bash
    curl --request GET \
      --url https://api.public.com/userapigateway/trading/{ACCOUNT_ID}/portfolio/v2 \
      --header 'Authorization: Bearer YOUR_ACCESS_TOKEN'
    ```

### Task 4.3: Documentation and Usage Examples
**Files**: README.md, usage guides
**Priority**: Low

- [ ] Update README.md with new commands
  - [ ] Add `open_position` and `close_position` examples
  - [ ] Document command syntax and parameters
  - [ ] Include risk management best practices
- [ ] Create comprehensive usage examples
  - [ ] **Buy a call**: `open_position AAPL 2024-02-16 C 145.00 1 --execute`
  - [ ] **Sell a put**: `open_position SPY 2024-01-19 P 420.00 -2 --execute`
  - [ ] **Close existing position**: `close_position AAPL 2024-02-16 C 145.00 1 --execute`
  - [ ] **Dry-run testing**: `open_position TSLA 2024-03-15 C 200.00 1` (no --execute)
- [ ] Document expected API responses and error handling
- [ ] Add troubleshooting guide for common issues

## Phase 5: Enhancement and Polish

### Task 5.1: Advanced Features
**Priority**: Low

- [ ] Add support for Good-Till-Canceled (GTC) orders
- [ ] Implement automatic position monitoring
- [ ] Add profit/loss target functionality
- [ ] Support for complex order types (stop-loss, etc.)

### Task 5.2: Performance and Optimization
**Priority**: Low

- [ ] Optimize quote retrieval for single options
- [ ] Cache option chain data to reduce API calls
- [ ] Improve error handling and recovery
- [ ] Add metrics and monitoring

---

## Implementation Priority

1. **Phase 1** (Core Infrastructure) - Required foundation
2. **Phase 2** (Shell Commands) - User interface implementation  
3. **Phase 3** (API Integration) - Order execution functionality
4. **Phase 4** (Testing) - Quality assurance
5. **Phase 5** (Enhancements) - Nice-to-have features

## Estimated Total Effort
We're going to implement this together - no estimates needed!

## Risk Considerations
- API compatibility with single-leg orders
- Position validation accuracy
- Walk limit pricing for single options vs spreads
- Order execution reliability for various option types