#!/usr/bin/env python3
"""
Command-line interface for the Public Brokerage API.
Usage: python cli.py <command> [options]

Commands:
  accounts                   - List all accounts
  portfolio <account_id>     - Show account portfolio
  history <account_id>       - Show account history
  instruments               - List all instruments (first 100)
  instrument <symbol>       - Get specific instrument details
  quote <symbol>            - Get real-time quote
  options <symbol>          - Get option expirations for symbol
  chain <symbol> <exp>      - Get option chain for symbol and expiration
  greeks <symbol>           - Get option Greeks for symbol
  help                      - Show this help message

Examples:
  python cli.py accounts
  python cli.py portfolio ACCOUNT123
  python cli.py quote AAPL
  python cli.py options SPY
  python cli.py chain SPY 2024-01-19
"""

import os
import sys
import argparse
from datetime import datetime
from dotenv import load_dotenv

from public_brokerage.client import PublicBrokerageClient
from public_brokerage.auth import create_access_token
from public_brokerage.accounts import get_accounts, get_account_portfolio, get_account_history
from public_brokerage.instruments import get_all_instruments, get_instrument
from public_brokerage.market_data import get_quotes, get_option_expirations, get_option_chain, get_option_greeks

# Load environment variables
load_dotenv()

def format_currency(amount):
    """Format currency amount for display."""
    if amount is None:
        return "N/A"
    return f"${amount:,.2f}"

def format_percentage(pct):
    """Format percentage for display."""
    if pct is None:
        return "N/A"
    return f"{pct:.2f}%"

def cmd_accounts(client):
    """List all accounts."""
    accounts = get_accounts(client)
    
    print(f"\n📊 Found {len(accounts)} account(s):")
    print("-" * 60)
    
    for account in accounts:
        print(f"Account ID: {account.accountId}")
        print(f"Type:       {account.accountType}")
        print(f"Status:     {account.status}")
        if account.dayTradingBuyingPower:
            print(f"Day Trading Power: {format_currency(account.dayTradingBuyingPower)}")
        if account.buyingPower:
            print(f"Buying Power:      {format_currency(account.buyingPower)}")
        print("-" * 60)

def cmd_portfolio(client, account_id):
    """Show account portfolio."""
    portfolio = get_account_portfolio(client, account_id)
    
    print(f"\n📈 Portfolio for Account {account_id}:")
    print("=" * 80)
    
    # Account summary
    print(f"Total Equity:      {format_currency(portfolio.totalEquity)}")
    print(f"Long Market Value: {format_currency(portfolio.longMarketValue)}")
    print(f"Short Market Value: {format_currency(portfolio.shortMarketValue)}")
    print(f"Day P&L:           {format_currency(portfolio.dayPL)}")
    print(f"Total P&L:         {format_currency(portfolio.totalPL)}")
    print("-" * 80)
    
    # Positions
    if portfolio.positions:
        print(f"\n📍 Positions ({len(portfolio.positions)}):")
        print("-" * 100)
        print(f"{'Symbol':<10} {'Qty':<8} {'Price':<10} {'Market Value':<15} {'P&L':<12} {'P&L %':<8}")
        print("-" * 100)
        
        for pos in portfolio.positions:
            print(f"{pos.symbol:<10} {pos.quantity:<8} "
                  f"{format_currency(pos.averagePrice):<10} "
                  f"{format_currency(pos.marketValue):<15} "
                  f"{format_currency(pos.unrealizedPL):<12} "
                  f"{format_percentage(pos.unrealizedPLPercent):<8}")
    else:
        print("\n📍 No positions found")

def cmd_history(client, account_id):
    """Show account history."""
    history = get_account_history(client, account_id)
    
    print(f"\n📜 Account History for {account_id}:")
    print("=" * 100)
    
    if history.activities:
        print(f"Found {len(history.activities)} activities:")
        print("-" * 100)
        print(f"{'Date':<12} {'Type':<15} {'Symbol':<10} {'Qty':<8} {'Price':<10} {'Amount':<12}")
        print("-" * 100)
        
        for activity in history.activities[:20]:  # Show last 20
            date_str = activity.date.strftime('%Y-%m-%d') if activity.date else 'N/A'
            print(f"{date_str:<12} {activity.type:<15} {getattr(activity, 'symbol', 'N/A'):<10} "
                  f"{getattr(activity, 'quantity', 'N/A'):<8} "
                  f"{format_currency(getattr(activity, 'price', None)):<10} "
                  f"{format_currency(getattr(activity, 'amount', None)):<12}")
        
        if len(history.activities) > 20:
            print(f"... and {len(history.activities) - 20} more activities")
    else:
        print("No activities found")

def cmd_instruments(client):
    """List instruments."""
    instruments = get_all_instruments(client, limit=100)
    
    print(f"\n🔍 Found {len(instruments)} instruments (showing first 100):")
    print("-" * 80)
    print(f"{'Symbol':<10} {'Name':<30} {'Type':<15} {'Active':<8}")
    print("-" * 80)
    
    for inst in instruments:
        name = (inst.name[:27] + '...') if len(inst.name) > 30 else inst.name
        print(f"{inst.symbol:<10} {name:<30} {inst.instrumentType:<15} {inst.active}")

def cmd_instrument(client, symbol):
    """Get instrument details."""
    instrument = get_instrument(client, symbol)
    
    print(f"\n🔍 Instrument Details for {symbol}:")
    print("=" * 60)
    print(f"Symbol:      {instrument.symbol}")
    print(f"Name:        {instrument.name}")
    print(f"Type:        {instrument.instrumentType}")
    print(f"Active:      {instrument.active}")
    print(f"Tradable:    {instrument.tradable}")
    if hasattr(instrument, 'optionType') and instrument.optionType:
        print(f"Option Type: {instrument.optionType}")
    if hasattr(instrument, 'strikePrice') and instrument.strikePrice:
        print(f"Strike:      {format_currency(instrument.strikePrice)}")
    if hasattr(instrument, 'expirationDate') and instrument.expirationDate:
        print(f"Expiration:  {instrument.expirationDate}")

def cmd_quote(client, symbol):
    """Get real-time quote."""
    quotes = get_quotes(client, [symbol])
    
    if not quotes:
        print(f"❌ No quote found for {symbol}")
        return
    
    quote = quotes[0]
    print(f"\n💰 Quote for {symbol}:")
    print("=" * 50)
    print(f"Last Price:   {format_currency(quote.last)}")
    print(f"Bid:          {format_currency(quote.bid)} x {quote.bidSize}")
    print(f"Ask:          {format_currency(quote.ask)} x {quote.askSize}")
    print(f"Volume:       {quote.volume:,}")
    print(f"Change:       {format_currency(quote.change)} ({format_percentage(quote.changePercent)})")
    print(f"High:         {format_currency(quote.high)}")
    print(f"Low:          {format_currency(quote.low)}")
    print(f"52W High:     {format_currency(quote.fiftyTwoWeekHigh)}")
    print(f"52W Low:      {format_currency(quote.fiftyTwoWeekLow)}")

def cmd_options(client, symbol):
    """Get option expirations."""
    expirations = get_option_expirations(client, symbol)
    
    print(f"\n📅 Option Expirations for {symbol}:")
    print("=" * 40)
    
    if expirations.expirationDates:
        for exp_date in expirations.expirationDates:
            print(f"  {exp_date}")
        print(f"\nTotal: {len(expirations.expirationDates)} expiration dates")
    else:
        print("No option expirations found")

def cmd_chain(client, symbol, expiration):
    """Get option chain."""
    chain = get_option_chain(client, symbol, expiration)
    
    print(f"\n⛓️  Option Chain for {symbol} expiring {expiration}:")
    print("=" * 120)
    
    if chain.options:
        print(f"{'Strike':<8} {'Call Symbol':<20} {'Call Last':<10} {'Call Bid/Ask':<15} "
              f"{'Put Symbol':<20} {'Put Last':<10} {'Put Bid/Ask':<15}")
        print("-" * 120)
        
        # Group by strike price
        strikes = {}
        for option in chain.options:
            strike = option.strikePrice
            if strike not in strikes:
                strikes[strike] = {'call': None, 'put': None}
            
            if option.optionType == 'call':
                strikes[strike]['call'] = option
            else:
                strikes[strike]['put'] = option
        
        for strike in sorted(strikes.keys()):
            call_opt = strikes[strike]['call']
            put_opt = strikes[strike]['put']
            
            call_symbol = call_opt.symbol if call_opt else 'N/A'
            call_last = format_currency(call_opt.last) if call_opt and call_opt.last else 'N/A'
            call_bid_ask = f"{format_currency(call_opt.bid)}/{format_currency(call_opt.ask)}" if call_opt else 'N/A'
            
            put_symbol = put_opt.symbol if put_opt else 'N/A'
            put_last = format_currency(put_opt.last) if put_opt and put_opt.last else 'N/A'
            put_bid_ask = f"{format_currency(put_opt.bid)}/{format_currency(put_opt.ask)}" if put_opt else 'N/A'
            
            print(f"{format_currency(strike):<8} {call_symbol:<20} {call_last:<10} {call_bid_ask:<15} "
                  f"{put_symbol:<20} {put_last:<10} {put_bid_ask:<15}")
        
        print(f"\nTotal: {len(chain.options)} options")
    else:
        print("No options found for this expiration")

def cmd_greeks(client, symbol):
    """Get option Greeks."""
    greeks = get_option_greeks(client, symbol)
    
    print(f"\n🔢 Option Greeks for {symbol}:")
    print("=" * 100)
    
    if greeks.greeks:
        print(f"{'Symbol':<20} {'Delta':<8} {'Gamma':<8} {'Theta':<8} {'Vega':<8} {'Rho':<8} {'IV':<8}")
        print("-" * 100)
        
        for greek in greeks.greeks:
            print(f"{greek.symbol:<20} {greek.delta:<8.4f} {greek.gamma:<8.4f} "
                  f"{greek.theta:<8.4f} {greek.vega:<8.4f} {greek.rho:<8.4f} "
                  f"{greek.impliedVolatility:<8.2%}")
        
        print(f"\nTotal: {len(greeks.greeks)} option Greeks")
    else:
        print("No Greeks found")

def show_help():
    """Show help message."""
    print(__doc__)

def main():
    """Main CLI function."""
    if len(sys.argv) < 2:
        show_help()
        return
    
    command = sys.argv[1].lower()
    
    if command == 'help':
        show_help()
        return
    
    # Check for API token
    secret_token = os.getenv("PUBLIC_SECRET_TOKEN")
    if not secret_token:
        print("❌ Error: PUBLIC_SECRET_TOKEN environment variable is required")
        print("   Please copy .env.example to .env and add your secret token")
        return
    
    try:
        with PublicBrokerageClient(secret_token=secret_token) as client:
            # Create access token
            create_access_token(client=client)
            
            if command == 'accounts':
                cmd_accounts(client)
            
            elif command == 'portfolio':
                if len(sys.argv) < 3:
                    print("❌ Error: Account ID required")
                    print("Usage: python cli.py portfolio <account_id>")
                    return
                cmd_portfolio(client, sys.argv[2])
            
            elif command == 'history':
                if len(sys.argv) < 3:
                    print("❌ Error: Account ID required")
                    print("Usage: python cli.py history <account_id>")
                    return
                cmd_history(client, sys.argv[2])
            
            elif command == 'instruments':
                cmd_instruments(client)
            
            elif command == 'instrument':
                if len(sys.argv) < 3:
                    print("❌ Error: Symbol required")
                    print("Usage: python cli.py instrument <symbol>")
                    return
                cmd_instrument(client, sys.argv[2])
            
            elif command == 'quote':
                if len(sys.argv) < 3:
                    print("❌ Error: Symbol required")
                    print("Usage: python cli.py quote <symbol>")
                    return
                cmd_quote(client, sys.argv[2])
            
            elif command == 'options':
                if len(sys.argv) < 3:
                    print("❌ Error: Symbol required")
                    print("Usage: python cli.py options <symbol>")
                    return
                cmd_options(client, sys.argv[2])
            
            elif command == 'chain':
                if len(sys.argv) < 4:
                    print("❌ Error: Symbol and expiration required")
                    print("Usage: python cli.py chain <symbol> <expiration>")
                    print("Example: python cli.py chain SPY 2024-01-19")
                    return
                cmd_chain(client, sys.argv[2], sys.argv[3])
            
            elif command == 'greeks':
                if len(sys.argv) < 3:
                    print("❌ Error: Symbol required")
                    print("Usage: python cli.py greeks <symbol>")
                    return
                cmd_greeks(client, sys.argv[2])
            
            else:
                print(f"❌ Unknown command: {command}")
                show_help()
    
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nNote: Make sure your PUBLIC_SECRET_TOKEN is valid and has API access enabled.")

if __name__ == "__main__":
    main()
