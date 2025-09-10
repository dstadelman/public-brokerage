# Requirements

Create a python library to execute trades on Public brokerage using the API.

We need to support all these endpoints:

https://public.com/api/docs/resources/authorization/create-personal-access-token
https://public.com/api/docs/resources/list-accounts/get-accounts
https://public.com/api/docs/resources/account-details/get-account-portfolio-v2
https://public.com/api/docs/resources/account-details/get-history
https://public.com/api/docs/resources/instrument-details/get-all-instruments
https://public.com/api/docs/resources/instrument-details/get-instrument
https://public.com/api/docs/resources/market-data/get-quotes
https://public.com/api/docs/resources/market-data/get-option-expirations
https://public.com/api/docs/resources/market-data/get-option-chain
https://public.com/api/docs/resources/order-placement/preflight-single-leg
https://public.com/api/docs/resources/order-placement/preflight-multi-leg
https://public.com/api/docs/resources/order-placement/place-order
https://public.com/api/docs/resources/order-placement/place-multileg-order
https://public.com/api/docs/resources/order-placement/get-order
https://public.com/api/docs/resources/order-placement/cancel-order
https://public.com/api/docs/resources/option-details/get-option-greeks

Use the `requests` library to make HTTP requests.

Use `pydantic` to create models for request and response data.

Use `unittest` to create unit tests for the library.

Use `python-dotenv` to manage environment variables for API keys and other sensitive information. Create a `.env.example` file to show what variables are required.

# TASKS

## Phase 1: Project Setup & Infrastructure

### Task 1.1: Initialize Python Project Structure
- [x] Create `.gitignore` file with Python project exclusions
- [x] Create main package directory `public_brokerage/`
- [x] Create `__init__.py` files for package structure
- [x] Create `setup.py` or `pyproject.toml` for package configuration
- [x] Create `requirements.txt` with dependencies
- [x] Create `.env.example` file with required environment variables
- [x] Create `README.md` with usage instructions

### Task 1.2: Install Required Dependencies
- [ ] Install `requests` for HTTP requests
- [ ] Install `pydantic` for data models
- [ ] Install `python-dotenv` for environment variable management
- [ ] Install development dependencies: `black`, `flake8` (unittest is built-in)

## Phase 2: Core Infrastructure & Models

### Task 2.1: Create Base Client Class
- [x] Create `client.py` with base `PublicBrokerageClient` class
- [x] Implement authentication handling (access token management)
- [x] Implement base HTTP request methods with error handling
- [x] Add retry logic and rate limiting
- [x] Add logging functionality

### Task 2.2: Create Pydantic Models for API Responses
- [x] Create `models/` directory
- [x] Create `auth.py` - Authentication models (AccessTokenResponse)
- [x] Create `account.py` - Account models (Account, AccountType, BuyingPower)
- [x] Create `portfolio.py` - Portfolio models (Portfolio, Position, Equity)
- [x] Create `instrument.py` - Instrument models (Instrument, InstrumentType)
- [x] Create `order.py` - Order models (Order, OrderType, OrderStatus, OrderSide)
- [x] Create `market_data.py` - Market data models (Quote, OptionChain, OptionExpiration)
- [x] Create `common.py` - Common models and enums

## Phase 3: Authentication Implementation

### Task 3.1: Implement Authentication Functions
- [x] Create `auth.py` module
- [x] Implement `create_access_token()` function
  - Endpoint: `POST /userapiauthservice/personal/access-tokens`
  - Parameters: secret, validityInMinutes
  - Returns: AccessToken
- [x] Add token caching and refresh logic
- [x] Add environment variable support for secrets

## Phase 4: Account Management Functions

### Task 4.1: Implement Account List Function
- [x] Create `accounts.py` module
- [x] Implement `get_accounts()` function
  - Endpoint: `GET /userapigateway/trading/account`
  - Returns: List of Account objects
- [x] Add error handling for 401/404 responses

### Task 4.2: Implement Account Details Functions
- [x] Implement `get_account_portfolio()` function
  - Endpoint: `GET /userapigateway/trading/{accountId}/portfolio/v2`
  - Parameters: accountId
  - Returns: Portfolio object with positions, equity, orders
- [x] Implement `get_account_history()` function
  - Endpoint: `GET /userapigateway/trading/{accountId}/history`
  - Parameters: accountId, date filters
  - Returns: Account history data

## Phase 5: Instrument and Market Data Functions

### Task 5.1: Implement Instrument Functions
- [x] Create `instruments.py` module
- [x] Implement `get_all_instruments()` function
  - Endpoint: `GET /userapigateway/trading/instruments`
  - Returns: List of all available instruments
- [x] Implement `get_instrument()` function
  - Endpoint: `GET /userapigateway/trading/instruments/{symbol}/{type}`
  - Parameters: symbol, type
  - Returns: Instrument details

### Task 5.2: Implement Market Data Functions
- [x] Create `market_data.py` module
- [x] Implement `get_quotes()` function
  - Endpoint: `POST /userapigateway/marketdata/{accountId}/quotes`
  - Parameters: accountId, List of instruments
  - Returns: List of Quote objects
- [x] Implement `get_option_expirations()` function
  - Endpoint: `POST /userapigateway/marketdata/{accountId}/option-expirations`
  - Parameters: accountId, instrument
  - Returns: List of expiration dates
- [x] Implement `get_option_chain()` function
  - Endpoint: `POST /userapigateway/marketdata/{accountId}/option-chain`
  - Parameters: accountId, instrument, expiration date
  - Returns: Option chain data
- [x] Implement `get_option_greeks()` function
  - Endpoint: `GET /userapigateway/option-details/{accountId}/{osiOptionSymbol}/greeks`
  - Parameters: accountId, option symbol
  - Returns: Option Greeks data

## Phase 6: Order Management Functions

### Task 6.1: Implement Order Preflight Functions
- [x] Create `orders.py` module
- [x] Implement `preflight_single_leg()` function
  - Endpoint: `POST /userapigateway/trading/{accountId}/preflight/single-leg`
  - Parameters: accountId, order details
  - Returns: Preflight validation results
- [x] Implement `preflight_multi_leg()` function
  - Endpoint: `POST /userapigateway/trading/{accountId}/preflight/multi-leg`
  - Parameters: accountId, multi-leg order details
  - Returns: Preflight validation results

### Task 6.2: Implement Order Placement Functions
- [x] Implement `place_order()` function
  - Endpoint: `POST /userapigateway/trading/{accountId}/order`
  - Parameters: accountId, order details (symbol, quantity, type, side, etc.)
  - Returns: Order confirmation
- [x] Implement `place_multileg_order()` function
  - Endpoint: `POST /userapigateway/trading/{accountId}/order/multileg`
  - Parameters: accountId, multi-leg order details
  - Returns: Multi-leg order confirmation

### Task 6.3: Implement Order Management Functions
- [x] Implement `get_order()` function
  - Endpoint: `GET /userapigateway/trading/{accountId}/order/{orderId}`
  - Parameters: accountId, orderId
  - Returns: Order details and status
- [x] Implement `cancel_order()` function
  - Endpoint: `DELETE /userapigateway/trading/{accountId}/order/{orderId}`
  - Parameters: accountId, orderId
  - Returns: Cancellation confirmation

## Phase 7: Testing & Documentation

### Task 7.1: Create Unit Tests (using unittest)
- [x] Create `tests/` directory
- [x] Create `test_client.py` - Test base client functionality using `unittest.TestCase`
- [x] Create `test_auth.py` - Test authentication functions using `unittest.TestCase`
- [ ] Create `test_accounts.py` - Test account management functions using `unittest.TestCase`
- [ ] Create `test_instruments.py` - Test instrument functions using `unittest.TestCase`
- [ ] Create `test_market_data.py` - Test market data functions using `unittest.TestCase`
- [ ] Create `test_orders.py` - Test order management functions using `unittest.TestCase`
- [x] Create mock responses for all API endpoints using `unittest.mock`
- [x] Use `unittest.mock.patch` for HTTP request mocking
- [ ] Achieve 90%+ test coverage using `coverage` package

### Task 7.2: Integration Tests (using unittest)
- [ ] Create `test_integration.py` with end-to-end tests using `unittest.TestCase` (requires API credentials)
- [ ] Test complete trading workflows
- [ ] Test error handling scenarios
- [ ] Test rate limiting and retry logic
- [ ] Use `unittest.skipIf` to conditionally skip tests when API credentials not available

### Task 7.3: Documentation
- [x] Update `README.md` with comprehensive usage examples
- [x] Add docstrings to all public functions and classes
- [x] Create `examples/` directory with sample scripts
- [x] Document error handling and best practices

## Phase 8: Advanced Features & Polish

### Task 8.1: Advanced Features
- [ ] Add async support with `aiohttp` (optional)
- [ ] Add WebSocket support for real-time data (if available)
- [ ] Add portfolio analysis utilities
- [ ] Add trading strategy helpers

### Task 8.2: Code Quality & CI/CD
- [ ] Set up GitHub Actions for CI/CD with `python -m unittest discover` for test execution
- [ ] Add code formatting with `black`
- [ ] Add linting with `flake8` or `pylint`
- [ ] Add type checking with `mypy`
- [ ] Add test coverage reporting with `coverage run -m unittest discover`
- [ ] Add pre-commit hooks

## Complete API Endpoint Analysis

**✅ ALL 16 ENDPOINTS VERIFIED AND ANALYZED**

| # | Endpoint | Method | Function Name | Module | Request Types | Response Types | Status |
|---|----------|---------|---------------|---------|---------------|----------------|---------|
| 1 | `/userapiauthservice/personal/access-tokens` | POST | `create_access_token()` | auth.py | `{secret: str, validityInMinutes?: int}` | `{accessToken: str}` | ✅ |
| 2 | `/userapigateway/trading/account` | GET | `get_accounts()` | accounts.py | None | `{accounts: Account[]}` | ✅ |
| 3 | `/userapigateway/trading/{accountId}/portfolio/v2` | GET | `get_account_portfolio()` | accounts.py | `accountId: str` | `Portfolio` with positions, equity, orders | ✅ |
| 4 | `/userapigateway/trading/{accountId}/history` | GET | `get_account_history()` | accounts.py | `accountId: str, start?: datetime, end?: datetime, pageSize?: int, nextToken?: str` | `{transactions: Transaction[], nextToken?: str, start: datetime, end: datetime, pageSize: int}` | ✅ |
| 5 | `/userapigateway/trading/instruments` | GET | `get_all_instruments()` | instruments.py | `typeFilter?: str[], tradingFilter?: str[], fractionalTradingFilter?: str[], optionTradingFilter?: str[], optionSpreadTradingFilter?: str[]` | `{instruments: InstrumentWithTrading[]}` | ✅ |
| 6 | `/userapigateway/trading/instruments/{symbol}/{type}` | GET | `get_instrument()` | instruments.py | `symbol: str, type: str` | `InstrumentWithTrading` | ✅ |
| 7 | `/userapigateway/marketdata/{accountId}/quotes` | POST | `get_quotes()` | market_data.py | `accountId: str, {instruments: Instrument[]}` | `{quotes: Quote[]}` | ✅ |
| 8 | `/userapigateway/marketdata/{accountId}/option-expirations` | POST | `get_option_expirations()` | market_data.py | `accountId: str, {instrument: Instrument}` | `{baseSymbol: str, expirations: date[]}` | ✅ |
| 9 | `/userapigateway/marketdata/{accountId}/option-chain` | POST | `get_option_chain()` | market_data.py | `accountId: str, {instrument: Instrument, expirationDate: date}` | `{baseSymbol: str, calls: Quote[], puts: Quote[]}` | ✅ |
| 10 | `/userapigateway/trading/{accountId}/preflight/single-leg` | POST | `preflight_single_leg()` | orders.py | `accountId: str, SingleLegOrderRequest` | `PreflightResponse` | ✅ |
| 11 | `/userapigateway/trading/{accountId}/preflight/multi-leg` | POST | `preflight_multi_leg()` | orders.py | `accountId: str, MultiLegOrderRequest` | `MultiLegPreflightResponse` | ✅ |
| 12 | `/userapigateway/trading/{accountId}/order` | POST | `place_order()` | orders.py | `accountId: str, OrderRequest` | `{orderId: uuid}` | ✅ |
| 13 | `/userapigateway/trading/{accountId}/order/multileg` | POST | `place_multileg_order()` | orders.py | `accountId: str, MultiLegOrderRequest` | `{orderId: uuid}` | ✅ |
| 14 | `/userapigateway/trading/{accountId}/order/{orderId}` | GET | `get_order()` | orders.py | `accountId: str, orderId: uuid` | `OrderDetails` | ✅ |
| 15 | `/userapigateway/trading/{accountId}/order/{orderId}` | DELETE | `cancel_order()` | orders.py | `accountId: str, orderId: uuid` | `None (204)` | ✅ |
| 16 | `/userapigateway/option-details/{accountId}/{osiOptionSymbol}/greeks` | GET | `get_option_greeks()` | market_data.py | `accountId: str, osiOptionSymbol: str` | `OptionGreeks` | ✅ |

## Detailed Response Type Definitions

### Core Data Types Found:

**Account Types:**
```python
Account = {
    accountId: str,
    accountType: "BROKERAGE" | "HIGH_YIELD" | "BOND_ACCOUNT" | "RIA_ASSET" | "TREASURY" | "TRADITIONAL_IRA" | "ROTH_IRA",
    optionsLevel: "NONE" | ...,
    brokerageAccountType: "CASH" | ...,
    tradePermissions: "BUY_AND_SELL" | ...
}
```

**Portfolio Types:**
```python
Portfolio = {
    accountId: str,
    accountType: AccountType,
    buyingPower: {
        cashOnlyBuyingPower: str,
        buyingPower: str,
        optionsBuyingPower: str
    },
    equity: [{ type: "CASH", value: str, percentageOfPortfolio: str }],
    positions: Position[],
    orders: Order[]
}

Position = {
    instrument: Instrument,
    quantity: str,
    openedAt: datetime,
    currentValue: str,
    percentOfPortfolio: str,
    lastPrice: { lastPrice: str, timestamp: datetime },
    instrumentGain: { gainValue: str, gainPercentage: str, timestamp: datetime },
    positionDailyGain: { gainValue: str, gainPercentage: str, timestamp: datetime },
    costBasis: { totalCost: str, unitCost: str, gainValue: str, gainPercentage: str, lastUpdate: datetime }
}
```

**Transaction Types:**
```python
Transaction = {
    timestamp: datetime,
    id: str,
    type: "TRADE" | ...,
    subType: "DEPOSIT" | ...,
    accountNumber: str,
    symbol: str,
    securityType: "EQUITY" | ...,
    side: "BUY" | "SELL",
    description: str,
    netAmount: str,
    principalAmount: str,
    quantity: str,
    direction: "INCOMING" | "OUTGOING",
    fees: str
}
```

**Instrument Types:**
```python
Instrument = {
    symbol: str,
    type: "EQUITY" | "OPTION" | "INDEX" | "MULTI_LEG_INSTRUMENT" | "UNDERLYING_SECURITY_FOR_INDEX_OPTION"
}

InstrumentWithTrading = {
    instrument: Instrument,
    trading: "BUY_AND_SELL" | "LIQUIDATION_ONLY" | "DISABLED",
    fractionalTrading: "BUY_AND_SELL" | "LIQUIDATION_ONLY" | "DISABLED",
    optionTrading: "BUY_AND_SELL" | "LIQUIDATION_ONLY" | "DISABLED",
    optionSpreadTrading: "BUY_AND_SELL" | "LIQUIDATION_ONLY" | "DISABLED"
}
```

**Quote Types:**
```python
Quote = {
    instrument: Instrument,
    outcome: "SUCCESS" | "FAILURE",
    last: str,
    lastTimestamp: datetime,
    bid: str,
    bidSize: int,
    bidTimestamp: datetime,
    ask: str,
    askSize: int,
    askTimestamp: datetime,
    volume: int,
    openInterest: int
}
```

**Order Types:**
```python
OrderRequest = {
    orderId: uuid,  # Required for deduplication
    instrument: Instrument,
    orderSide: "BUY" | "SELL",
    orderType: "MARKET" | "LIMIT" | "STOP" | "STOP_LIMIT",
    expiration: { timeInForce: "DAY" | ..., expirationTime?: datetime },
    quantity?: str,  # Mutually exclusive with amount
    amount?: str,    # Mutually exclusive with quantity
    limitPrice?: str,  # Required for LIMIT and STOP_LIMIT
    stopPrice?: str,   # Required for STOP and STOP_LIMIT
    openCloseIndicator?: "OPEN" | "CLOSE"  # For options only
}

OrderDetails = {
    orderId: uuid,
    instrument: Instrument,
    createdAt: datetime,
    type: "MARKET" | "LIMIT" | "STOP" | "STOP_LIMIT",
    side: "BUY" | "SELL",
    status: "NEW" | "PARTIALLY_FILLED" | "CANCELLED" | "QUEUED_CANCELLED" | "FILLED" | "REJECTED" | "PENDING_REPLACE" | "PENDING_CANCEL" | "EXPIRED" | "REPLACED",
    quantity?: str,
    notionalValue?: str,
    expiration: { timeInForce: str, expirationTime?: datetime },
    limitPrice?: str,
    stopPrice?: str,
    closedAt?: datetime,
    openCloseIndicator?: "OPEN" | "CLOSE",
    filledQuantity?: str,
    averagePrice?: str,
    legs?: OrderLeg[],  # For multi-leg orders
    rejectReason?: str
}
```

**Preflight Types:**
```python
PreflightResponse = {
    instrument: Instrument,
    cusip: str,
    rootSymbol: str,
    rootOptionSymbol: str,
    estimatedCommission: str,
    regulatoryFees: {
        secFee: str,     # SEC fee for sell orders
        tafFee: str,     # Trading Activity Fee (FINRA)
        orfFee: str,     # Options Regulatory Fee
        exchangeFee: str, # Exchange fee for index options
        occFee: str,     # Options Clearing Corporation Fee
        catFee: str      # Consolidated Audit Trail Fee
    },
    estimatedIndexOptionFee: str,
    orderValue: str,
    estimatedQuantity: str,
    estimatedCost: str,
    buyingPowerRequirement: str,
    estimatedProceeds: str,
    optionDetails?: {
        baseSymbol: str,
        type: "CALL" | "PUT",
        strikePrice: str,
        optionExpireDate: date
    },
    estimatedOrderRebate?: {
        estimatedOptionRebate: str,
        optionRebatePercent: int,
        perContractRebate: str
    },
    marginRequirement?: {
        longMaintenanceRequirement: str,
        longInitialRequirement: str
    },
    marginImpact?: {
        marginUsageImpact: str,
        initialMarginRequirement: str
    },
    priceIncrement?: {
        incrementBelow3: str,
        incrementAbove3: str,
        currentIncrement: str
    }
}
```

**Option Types:**
```python
OptionGreeks = {
    delta: str,              # Price sensitivity to underlying
    gamma: str,              # Rate of change of delta
    theta: str,              # Time decay
    vega: str,               # Volatility sensitivity
    rho: str,                # Interest rate sensitivity
    impliedVolatility: str   # Implied volatility forecast
}

MultiLegOrderRequest = {
    orderId: uuid,
    quantity: int,
    type: "LIMIT",  # Only LIMIT orders allowed for multi-leg
    limitPrice: str,  # Positive for debit spreads, negative for credit spreads
    expiration: { timeInForce: str, expirationTime?: datetime },
    legs: OrderLeg[]  # 2-6 legs, max 1 equity leg
}

OrderLeg = {
    instrument: Instrument,
    side: "BUY" | "SELL",
    openCloseIndicator: "OPEN" | "CLOSE",
    ratioQuantity: int
}
```

**Legend:** ⏳ = Pending, ✅ = Complete, ❌ = Failed/Blocked

