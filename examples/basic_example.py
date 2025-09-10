"""
Basic example showing how to authenticate and get account information.
"""

import os
import sys
from dotenv import load_dotenv

# Add the parent directory to the path so we can import from public_brokerage
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from public_brokerage.client import PublicBrokerageClient
from public_brokerage.auth import create_access_token
from public_brokerage.accounts import get_accounts, get_account_portfolio

# Load environment variables
load_dotenv()

def main():
    # Get secret token from environment
    secret_token = os.getenv("PUBLIC_SECRET_TOKEN")
    if not secret_token:
        print("Error: PUBLIC_SECRET_TOKEN environment variable is required")
        print("Please set it in your .env file")
        return
    
    # Create client with context manager for automatic cleanup
    with PublicBrokerageClient(secret_token=secret_token, debug=True) as client:
        try:
            # Create access token
            print("Creating access token...")
            access_token = create_access_token(client=client)
            print(f"✓ Access token created: {access_token[:20]}...")
            
            # Get accounts
            print("\nFetching accounts...")
            accounts = get_accounts(client)
            print(f"✓ Found {len(accounts)} accounts")
            
            # Display account information
            for i, account in enumerate(accounts, 1):
                print(f"\nAccount {i}:")
                print(f"  ID: {account.accountId}")
                print(f"  Type: {account.accountType}")
                print(f"  Options Level: {account.optionsLevel}")
                print(f"  Account Type: {account.brokerageAccountType}")
                print(f"  Trade Permissions: {account.tradePermissions}")
                
                # Get portfolio for first account
                if i == 1:
                    print(f"\nFetching portfolio for account {account.accountId}...")
                    try:
                        portfolio = get_account_portfolio(client, account.accountId)
                        print(f"✓ Portfolio loaded")
                        print(f"  Buying Power: ${portfolio.buyingPower.buyingPower}")
                        print(f"  Cash Buying Power: ${portfolio.buyingPower.cashOnlyBuyingPower}")
                        print(f"  Options Buying Power: ${portfolio.buyingPower.optionsBuyingPower}")
                        print(f"  Positions: {len(portfolio.positions)}")
                        print(f"  Open Orders: {len(portfolio.orders)}")
                        
                        # Show equity breakdown
                        print("  Equity Breakdown:")
                        for equity in portfolio.equity:
                            print(f"    {equity.type}: ${equity.value} ({equity.percentageOfPortfolio}%)")
                        
                        # Show some positions
                        if portfolio.positions:
                            print("  Sample Positions:")
                            for pos in portfolio.positions[:3]:  # Show first 3
                                print(f"    {pos.instrument.symbol}: {pos.quantity} shares, ${pos.currentValue}")
                    
                    except Exception as e:
                        print(f"✗ Error fetching portfolio: {e}")
            
            print("\n✓ Example completed successfully!")
            
        except Exception as e:
            print(f"✗ Error: {e}")

if __name__ == "__main__":
    main()
