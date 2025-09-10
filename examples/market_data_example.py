"""
Market data example showing how to get quotes and option data.
"""

import os
import sys
from dotenv import load_dotenv
from datetime import date

# Add the parent directory to the path so we can import from public_brokerage
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from public_brokerage.client import PublicBrokerageClient
from public_brokerage.accounts import get_accounts
from public_brokerage.market_data import get_quotes, get_option_expirations, get_option_chain
from public_brokerage.models.common import Instrument, InstrumentType

# Load environment variables
load_dotenv()

def main():
    secret_token = os.getenv("PUBLIC_SECRET_TOKEN")
    if not secret_token:
        print("Error: PUBLIC_SECRET_TOKEN environment variable is required")
        return
    
    with PublicBrokerageClient(secret_token=secret_token) as client:
        try:
            # Get first account
            accounts = get_accounts(client)
            if not accounts:
                print("No accounts found")
                return
            
            account_id = accounts[0].accountId
            print(f"Using account: {account_id}")
            
            # Create some instruments to get quotes for
            instruments = [
                Instrument(symbol="AAPL", type=InstrumentType.EQUITY),
                Instrument(symbol="MSFT", type=InstrumentType.EQUITY),
                Instrument(symbol="TSLA", type=InstrumentType.EQUITY),
            ]
            
            # Get quotes
            print("\nFetching quotes...")
            quotes = get_quotes(client, account_id, instruments)
            
            for quote in quotes:
                if quote.outcome == "SUCCESS":
                    print(f"\n{quote.instrument.symbol}:")
                    print(f"  Last: ${quote.last} at {quote.lastTimestamp}")
                    print(f"  Bid: ${quote.bid} x {quote.bidSize}")
                    print(f"  Ask: ${quote.ask} x {quote.askSize}")
                    print(f"  Volume: {quote.volume:,}")
                else:
                    print(f"\n{quote.instrument.symbol}: Failed to get quote")
            
            # Get option expirations for AAPL
            print("\nFetching AAPL option expirations...")
            aapl = Instrument(symbol="AAPL", type=InstrumentType.EQUITY)
            
            try:
                expirations = get_option_expirations(client, account_id, aapl)
                print(f"Found {len(expirations)} expiration dates:")
                for exp in expirations[:5]:  # Show first 5
                    print(f"  {exp}")
                
                # Get option chain for first expiration
                if expirations:
                    first_exp = expirations[0]
                    print(f"\nFetching option chain for {first_exp}...")
                    
                    option_chain = get_option_chain(client, account_id, aapl, first_exp)
                    print(f"Base symbol: {option_chain.baseSymbol}")
                    print(f"Calls: {len(option_chain.calls)}")
                    print(f"Puts: {len(option_chain.puts)}")
                    
                    # Show some call options
                    print("\nSample Call Options:")
                    for call in option_chain.calls[:3]:
                        if call.outcome == "SUCCESS":
                            print(f"  {call.instrument.symbol}: Last=${call.last}, Bid=${call.bid}, Ask=${call.ask}")
                    
                    # Show some put options  
                    print("\nSample Put Options:")
                    for put in option_chain.puts[:3]:
                        if put.outcome == "SUCCESS":
                            print(f"  {put.instrument.symbol}: Last=${put.last}, Bid=${put.bid}, Ask=${put.ask}")
            
            except Exception as e:
                print(f"Error fetching option data: {e}")
            
            print("\n✓ Market data example completed!")
            
        except Exception as e:
            print(f"✗ Error: {e}")

if __name__ == "__main__":
    main()
