# Requirements

Create a shell UI for the commands in the `cli.py`.

In this UI, I can type different commands to interact with the Public Brokerage API.

something like

```bash
> accounts

# list accounts

> set default account 123456

# default set to account 123456

> show positions

# show positions for default account 123456

> show positions 654321

# show positions for account 654321

> open_call_spread AAPL 2024-07-19 170 2024-08-16 175 1

# run the background process to open a call spread, BUT do not actually place the orders, just run the preflight. Simulate running all the way to the ASK and then stopping if not filled.

> open_call_spread AAPL 2024-07-19 170 2024-08-16 175 1 --execute

# run the background process to open a call spread, and actually place the orders. Use default max_wait_time of 42 seconds.

> close_call_spread AAPL

# analyze the current position and the already running background processes.
# if there is already a background process running to close a call spread for AAPL, do nothing and inform the user.
# if there are no positions for AAPL, inform the user and do nothing.
# use logic to split the position into the correct number of background processes to close all the call spreads for AAPL.
# run the preflight check for each background process, simulating running all the way to the BID and then stopping if not filled.

> close_call_spread AAPL --execute

# same as above, but actually place the orders.
```

* Automatically log in using the token in the `.env` file.
* Automatically renew the token if expired.

* Commands to support:
    - list accounts
    - set account as "default" (should automatically set the last command as the default account for future commands and on restart)
    - show positions for default account (or with specified account id)
    - show option expirations for a given symbol
    - show option chain for a given symbol and expiration
    - open a call spread using walk limit order (runs in background)
        - args: symbol, short_expiration, short_strike, long_expiration, long_strike, quantity, max_wait_time (optional in seconds, default 42), execute (this is a flag, if not set just run the preflight and show what would be done)
        - process:
            - fetch current bid/ask spread for the call spread
            - divide the bid/ask spread into 20 increments (this is not practical if the bid/ask spread is less than .20, so in this case just use .01 increments, ie however many increments you can fit into the bid/ask spread up to 20)
            - place a preflight request to confirm the order can be placed
            - ONLY IF execute is true: place a limit order at the bid price + 1 increment
                - if not filled in max_wait_time minute:
                    - cancel the order
                    - confirm that it was cancelled
                    - preflight a new limit order at bid price + 2 increments
                    - only IF execute is true: place a new limit order at the bid price + 2 increments
            - repeat until filled (or we reach the ask price)
    - close a call spread using walk limit order (runs in background)
        - args: symbol, execute (this is a flag, if not set just run the preflight and show what would be done)
        - optional args: max_wait_time (in seconds)
        - use the current positions to elucidate the call spreads.
            - there might be multiple call spreads for the same symbol... so we have to handle this case.
            - example simple: 1 spread
                - 2 short call
                - 2 long call
                - ANSWER: this can be done in one background process, closing both legs at the same time
            - example complex: 10 spreads with different strikes
                - 10 short calls
                - 5 calls at one strike
                - 5 calls at another strike
                - ANSWER: this will have to be split into TWO background processes, closing 5 with one long strike and 5 with another long strike
        - we use the same walk limit as above, BUT we are trying to SELL the call spread, so we start at the ASK price and walk down to the BID price.
        

# Tasks

## Core Shell Infrastructure
- [x] Create `shell.py` - Main interactive shell program
- [x] Implement persistent session management with user state
- [x] Create config file (`~/.public_brokerage_config.json`) for storing default account
- [x] Implement automatic authentication with token refresh
- [x] Create command parser with support for flags and arguments
- [x] Implement command history and auto-completion
- [x] Add colored output and formatting for better UX

## Basic Commands
- [x] Implement `accounts` command - List all available accounts
- [x] Implement `set default account <account_id>` command - Set default account for session
- [x] Implement `show positions [account_id]` command - Show positions for default or specified account
- [x] Implement `show options <symbol>` command - Show option expirations for symbol
- [x] Implement `show chain <symbol> <expiration>` command - Show option chain
- [x] Implement `quote <symbol>` command - Get real-time quote
- [x] Implement `help` command - Show available commands and usage

## Options Position Analysis
- [x] Create `position_analyzer.py` - Analyze current positions to identify spreads
- [x] Implement spread detection logic for call spreads
- [x] Implement spread detection logic for put spreads
- [x] Handle complex positions with multiple spreads of same underlying
- [x] Create position grouping by underlying symbol and expiration

## Walk Limit Order Engine
- [x] Create `walk_limit_engine.py` - Background process manager for walk limit orders
- [x] Implement bid/ask spread calculation and increment logic
- [x] Implement order placement with incremental price walking
- [x] Add order monitoring and cancellation logic
- [x] Implement retry mechanism with exponential backoff
- [x] Add logging and status reporting for background processes
- [x] Implement process synchronization to prevent duplicate orders

## Order Confirmation System
- [x] Create `confirmation_card.py` - Display detailed order confirmation cards
- [x] Implement spread pricing calculator (bid/ask for the entire spread)
- [x] Create option information formatter (strike, expiration, type, Greeks)
- [x] Implement real-time market data fetching for confirmation display
- [x] Add Greeks data integration from options endpoint
- [x] Create interactive confirmation prompt (y/n/details/cancel)
- [x] Implement order summary with cost basis and risk analysis
- [x] Add market impact estimation and liquidity warnings

## Confirmation Card Features
- [ ] **Opening Spread Confirmation Card:**
  - [ ] Display underlying symbol and current stock price
  - [ ] Show short leg: strike, expiration, bid/ask, Greeks (delta, gamma, theta, vega, rho)
  - [ ] Show long leg: strike, expiration, bid/ask, Greeks (delta, gamma, theta, vega, rho)
  - [ ] Calculate and display net spread bid/ask prices
  - [ ] Show maximum profit, maximum loss, and break-even point
  - [ ] Display net delta, gamma, theta, vega exposure
  - [ ] Show required buying power and margin impact
  - [ ] Display estimated commission costs
  - [ ] Show liquidity indicators (volume, open interest)
- [ ] **Closing Spread Confirmation Card:**
  - [ ] Display current position details (quantity, entry price, current P&L)
  - [ ] Show current bid/ask for closing the spread
  - [ ] Display current Greeks exposure being closed
  - [ ] Calculate closing cost/credit and net P&L impact
  - [ ] Show time decay impact if holding vs closing
  - [ ] Display days to expiration and theta burn
  - [ ] Show impact on overall portfolio Greeks and buying power
- [ ] **Enhanced Confirmation Features:**
  - [ ] Add real-time price updates while user reviews
  - [ ] Implement spread width and risk/reward ratio calculations
  - [ ] Add volatility analysis and IV rank information
  - [ ] Show probability of profit based on current market conditions
  - [ ] Display historical performance of similar spreads
  - [ ] Add warning alerts for unusual market conditions
  - [ ] Implement "details" option for extended analysis

## Open Call Spread Command
- [x] Implement `open_call_spread <symbol> <short_exp> <short_strike> <long_exp> <long_strike> <qty> [--max_wait_time=42] [--execute]`
- [x] Create multi-leg order construction for call spreads
- [x] Implement preflight validation for spread orders
- [x] Add current market data fetching for spread pricing
- [x] **Create confirmation card display before execution**
- [x] **Fetch and display Greeks for both legs of the spread**
- [x] **Show net credit/debit and break-even analysis**
- [x] **Implement user confirmation prompt with detailed spread info**
- [x] Implement dry-run mode (without --execute flag)
- [x] Add background process spawning for order execution (only after confirmation)
- [x] Implement real-time status updates during execution

## Close Call Spread Command  
- [x] Implement `close_call_spread <symbol> [--max_wait_time=42] [--execute]`
- [x] Create position analysis to identify existing call spreads
- [x] Handle multiple spreads for same underlying (split into separate processes)
- [x] **Create confirmation card for closing spreads**
- [x] **Show current position P&L and closing impact**
- [x] **Display current bid/ask for closing the spread**
- [x] **Show Greeks changes from closing the position**
- [x] **Implement confirmation prompt with closing analysis**
- [x] Implement spread closing logic (sell the spread)
- [x] Add conflict detection for already running close processes
- [x] Implement position validation before closing
- [x] Add support for partial closes and complex position scenarios

## Background Process Management
- [x] Create `process_manager.py` - Manage multiple concurrent trading processes
- [x] Implement process status tracking and reporting
- [x] Add process cancellation and cleanup
- [x] Implement process persistence across shell sessions
- [x] Add process conflict detection and resolution
- [x] Create process logging and audit trail
- [x] Implement process timeout and error handling

## Advanced Features
- [x] Add `status` command - Show all running background processes
- [x] Add `cancel <process_id>` command - Cancel specific background process
- [x] Add `cancel all` command - Cancel all running processes
- [x] Implement `logs <process_id>` command - Show process execution logs
- [ ] Add market hours validation for order placement
- [ ] Implement position size validation and risk checks
- [ ] Add support for put spreads (open_put_spread, close_put_spread)

## Error Handling & Validation
- [ ] Implement comprehensive input validation for all commands
- [ ] Add market data validation (valid symbols, expirations, strikes)
- [ ] Implement account balance and buying power checks
- [ ] Add order size and position limit validation
- [ ] Create user-friendly error messages and suggestions
- [ ] Implement graceful handling of API rate limits
- [ ] Add network connectivity checks and retry logic
