# WARNING

This code is **vibe-coded slop**. It may be useful if you're trying to implement your own API calls to Public.

Some problems I encountered with this code:

* The AI made some really dangerous decisions on how it was canceling orders—potentially increasing the size of trades way higher than intended. I *think* I fixed this, but I can't be sure there aren't more problems.
* The Public API seems to have some issues with concurrency. This code attempts to solve this problem by only sending one *account state modification* API call at a time.
    * I was simply blasting APIs, and an order got *stuck* such that I could not close it. The order went away at the end of the day (as it was supposed to), but the Public support folks could not cancel the order for me and have not given me a reason why it happened.

This is a personal project—and not meant to be used by general folks or to solve problems in general for all uses. Unfortunately I don't have time to maintain this code for everyone. Feel free to fork this project.

# Public Brokerage Trading Shell

A comprehensive Python trading system with an interactive shell interface for the Public Brokerage API. Features walk limit orders, sophisticated spread trading, and advanced position management.

## Features

- **Complete API Coverage**: All 16 Public API endpoints supported
- **Type Safety**: Full Pydantic models for request/response validation  
- **Authentication Management**: Automatic access token handling and refresh
- **Error Handling**: Comprehensive error handling with retries
- **Rate Limiting**: Built-in retry logic for rate-limited requests
- **Logging**: Configurable debug logging
- **Context Manager**: Clean resource management

## Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/yourusername/public-brokerage.git
cd public-brokerage
pip install -e .
```

## Project Structure

```
public-brokerage/
├── public_brokerage/          # Main library package
│   ├── models/               # Data models and schemas
│   ├── accounts.py           # Account management
│   ├── orders.py            # Order operations
│   ├── positions.py         # Position tracking
│   └── client.py            # HTTP client
├── shell.py                 # Interactive trading shell
├── walk_limit_engine.py     # Automated order management
├── *_test.py               # Unit tests (follow naming convention)
└── README.md               # This file
```

## Basic Usage
```

## Quick Start

### 1. Set up your environment

Create a `.env` file (copy from `.env.example`):

```bash
cp .env.example .env
```

Edit `.env` and add your Personal Secret Token from your Public account settings:

```
PUBLIC_SECRET_TOKEN=your_secret_token_here
```

### 2. Basic Usage

```python
import os
from dotenv import load_dotenv
from public_brokerage.client import PublicBrokerageClient
from public_brokerage.auth import create_access_token
from public_brokerage.accounts import get_accounts

# Load environment variables
load_dotenv()

# Create client
client = PublicBrokerageClient(
    secret_token=os.getenv("PUBLIC_SECRET_TOKEN"),
    debug=True  # Enable debug logging
)

# Create access token
access_token = create_access_token(client=client)
print(f"Access token: {access_token}")

# Get accounts
accounts = get_accounts(client)
print(f"Found {len(accounts)} accounts")

# Close client when done
client.close()
```

### 3. Using Context Manager

```python
from public_brokerage.client import PublicBrokerageClient
from public_brokerage.accounts import get_accounts, get_account_portfolio

# Use context manager for automatic cleanup
with PublicBrokerageClient(secret_token="your_token") as client:
    # Get accounts
    accounts = get_accounts(client)
    
    # Get portfolio for first account
    if accounts:
        portfolio = get_account_portfolio(client, accounts[0].accountId)
        print(f"Account {accounts[0].accountId} has {len(portfolio.positions)} positions")
```

## API Reference

### Authentication

```python
from public_brokerage.auth import create_access_token

# Create access token (15 minute validity by default)
token = create_access_token(secret="your_secret", validity_minutes=15)

# Or let it read from environment
token = create_access_token()  # Uses PUBLIC_SECRET_TOKEN env var
```

### Account Management

```python
from public_brokerage.accounts import get_accounts, get_account_portfolio, get_account_history
from datetime import datetime

# Get all accounts
accounts = get_accounts(client)

# Get portfolio for an account
portfolio = get_account_portfolio(client, account_id)

# Get account history with optional filters
history = get_account_history(
    client, 
    account_id,
    start=datetime(2024, 1, 1),
    end=datetime(2024, 12, 31),
    page_size=100
)
```

### Instruments

```python
from public_brokerage.instruments import get_all_instruments, get_instrument

# Get all instruments
instruments = get_all_instruments(client)

# Get specific instrument
instrument = get_instrument(client, "AAPL", "EQUITY")
```

### Market Data

```python
from public_brokerage.market_data import get_quotes, get_option_chain, get_option_greeks
from public_brokerage.models.common import Instrument, InstrumentType
from datetime import date

# Get quotes
instruments = [Instrument(symbol="AAPL", type=InstrumentType.EQUITY)]
quotes = get_quotes(client, account_id, instruments)

# Get option chain
underlying = Instrument(symbol="AAPL", type=InstrumentType.EQUITY)
option_chain = get_option_chain(client, account_id, underlying, date(2024, 1, 19))

# Get option Greeks
greeks = get_option_greeks(client, account_id, "AAPL  240119C00150000")
```

### Order Management

```python
from public_brokerage.orders import place_order, get_order, cancel_order, preflight_single_leg
from public_brokerage.models.order import OrderRequest
from public_brokerage.models.common import Instrument, InstrumentType, OrderSide, OrderType, Expiration, TimeInForce
import uuid

# Create order request
order_request = OrderRequest(
    orderId=str(uuid.uuid4()),
    instrument=Instrument(symbol="AAPL", type=InstrumentType.EQUITY),
    orderSide=OrderSide.BUY,
    orderType=OrderType.MARKET,
    expiration=Expiration(timeInForce=TimeInForce.DAY),
    quantity="1"
)

# Preflight the order (get cost estimates)
preflight = preflight_single_leg(client, account_id, order_request)
print(f"Estimated cost: ${preflight.estimatedCost}")

# Place the order
order_id = place_order(client, account_id, order_request)
print(f"Order placed: {order_id}")

# Check order status
order = get_order(client, account_id, order_id)
print(f"Order status: {order.status}")

# Cancel order if needed
cancel_order(client, account_id, order_id)
```

## Interactive Shell

The library includes an interactive shell interface for easy trading operations:

### Basic Usage

```bash
# Interactive mode - enter commands interactively
python shell.py

# Batch mode - pipe commands to shell
echo -e "accounts\npositions 12345678\nexit" | python shell.py
```

### Available Commands

- `accounts` - List all your accounts
- `positions [account_id]` - Show positions for an account
- `options <symbol>` - Show option expirations for symbol
- `chain <symbol> <expiration>` - Show option chain
- `quote <symbol>` - Get real-time quote
- `open_call_spread` - Open call spread with walk limit orders
- `close_call_spread` - Close call spreads with walk limit orders  
- `status` - Show all background process status
- `cancel <process_id>` - Cancel a specific process and its order
- `cancel all` - **Cancel ALL active processes and their broker orders**
- `logs <process_id>` - Show process execution logs
- `help` - Show all available commands
- `exit` - Exit the shell

### Walk Limit Orders

Use the walk limit engine to automatically manage partial fills and cancellations:

```bash
# In the shell
walk_limit 12345678 my_order.json
```

Example order JSON file:
```json
{
  "orderId": "unique-order-id",
  "instrument": {"symbol": "SPY", "type": "EQUITY"},
  "orderSide": "BUY",
  "orderType": "LIMIT",
  "expiration": {"timeInForce": "DAY"},
  "quantity": "10",
  "limitPrice": "420.50"
}
```

The walk limit engine will:
- Monitor for partial fills
- Automatically handle remaining quantities
- Provide real-time status updates
- Cancel unfilled portions when needed

### Important: Order Cancellation

⚠️ **CRITICAL**: The `cancel all` command will immediately cancel **ALL active orders** with your broker, not just stop the background processes. Use with extreme caution in live trading!

### Shell Features

- **Interactive Mode**: Full command history and auto-completion
- **Batch Mode**: Execute multiple commands with `-e` flag
- **Status Updates**: Real-time progress for long-running operations
- **Error Handling**: Graceful error messages and recovery
- **Position Tracking**: Monitor account positions and balances

## Error Handling

The library uses standard Python exceptions:

```python
import requests
from public_brokerage import PublicBrokerageClient
from public_brokerage.accounts import get_accounts

try:
    with PublicBrokerageClient(secret_token="invalid") as client:
        accounts = get_accounts(client)
except requests.exceptions.HTTPError as e:
    print(f"HTTP error: {e}")
except ValueError as e:
    print(f"Validation error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Configuration

### Environment Variables

- `PUBLIC_SECRET_TOKEN`: Your Personal Secret Token (required)
- `ACCESS_TOKEN_VALIDITY_MINUTES`: Default token validity (default: 15)
- `PUBLIC_API_BASE_URL`: API base URL (default: https://public.com)
- `REQUEST_TIMEOUT`: Request timeout in seconds (default: 30)
- `MAX_RETRIES`: Maximum retry attempts (default: 3)
- `DEBUG_LOGGING`: Enable debug logging (default: False)

### Client Configuration

```python
client = PublicBrokerageClient(
    secret_token="your_token",
    base_url="https://public.com",
    timeout=30,
    max_retries=3,
    debug=True
)
```

## Testing

Run the unit tests:

```bash
python -m unittest discover . -p "*_test.py"
```

Run specific test modules:

```bash
python -m unittest client_test
python -m unittest auth_test
python -m unittest walk_limit_engine_test
```

Run with coverage:

```bash
pip install coverage
coverage run -m unittest discover . -p "*_test.py"
coverage report
coverage html  # Generate HTML report
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for your changes
4. Ensure all tests pass
5. Submit a pull request

## Disclaimer

⚠️ **Important**: This library interacts with live trading accounts. Always test thoroughly in a paper trading environment first. You are responsible for all trades executed through this API.

The Public Individual API is for personal, non-commercial use only. See [Public's API terms](https://public.com/disclosures/individual-API-program) for details.

## License

MIT License - see LICENSE file for details.

## Support

- Documentation: [Public API Docs](https://public.com/api/docs)
- Issues: [GitHub Issues](https://github.com/yourusername/public-brokerage/issues)
- Email: [API Support](mailto:api-concierge@public.com)

