#!/usr/bin/env python3
"""
Interactive shell for the Public Brokerage API.
Provides a command-line interface for trading operations with walk limit orders.
"""

import os
import sys
import cmd
import shlex
import argparse
import signal
from typing import List, Dict, Optional
import logging
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv

# Import readline for command history support (up arrow)
try:
    import readline
    READLINE_AVAILABLE = True
except ImportError:
    try:
        # Try pyreadline3 on Windows
        import pyreadline3 as readline
        READLINE_AVAILABLE = True
    except ImportError:
        READLINE_AVAILABLE = False

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from public_brokerage.client import PublicBrokerageClient
from public_brokerage.auth import create_access_token, ensure_access_token
from public_brokerage.accounts import get_accounts, get_account_portfolio
from public_brokerage.market_data import get_quotes, get_option_expirations, get_option_chain
from public_brokerage.orders import preflight_single_leg
from config import config
from position_analyzer import PositionAnalyzer
from confirmation_card import ConfirmationCard
from walk_limit_engine import WalkLimitEngine

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_shell.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


class Colors:
    """ANSI color codes for terminal output."""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


class PublicBrokerageShell(cmd.Cmd):
    """Interactive shell for Public Brokerage API trading operations."""
    
    intro = f"""
{Colors.BOLD}{Colors.BLUE}
╔══════════════════════════════════════════════════════════════╗
║                   PUBLIC BROKERAGE SHELL                    ║
║                                                              ║
║  Interactive trading interface with walk limit orders       ║
║  Type 'help' for available commands                         ║
╚══════════════════════════════════════════════════════════════╝
{Colors.END}

Initializing...
"""
    
    prompt = f"{Colors.BOLD}{Colors.GREEN}> {Colors.END}"
    
    def __init__(self):
        super().__init__()
        self.client = None
        self.position_analyzer = None
        self.confirmation_card = None
        self.walk_engine = None
        self.accounts = []
        self.default_account = config.get_default_account()
        
        # Initialize command history (enables up arrow)
        self._setup_history()
        
        # Initialize the connection
        self._initialize()
    
    def _initialize(self):
        """Initialize the client and authenticate."""
        try:
            secret_token = os.getenv("PUBLIC_SECRET_TOKEN")
            if not secret_token:
                print(f"{Colors.RED}❌ Error: PUBLIC_SECRET_TOKEN environment variable is required{Colors.END}")
                print("   Please copy .env.example to .env and add your secret token")
                sys.exit(1)
            
            # Get additional configuration from environment
            base_url = os.getenv("PUBLIC_API_BASE_URL", "https://public.com")
            timeout = int(os.getenv("REQUEST_TIMEOUT", "30"))
            max_retries = int(os.getenv("MAX_RETRIES", "3"))
            debug = os.getenv("DEBUG_LOGGING", "False").lower() == "true"
            
            print("🔐 Authenticating...")
            self.client = PublicBrokerageClient(
                secret_token=secret_token,
                base_url=base_url,
                timeout=timeout,
                max_retries=max_retries,
                debug=debug
            )
            create_access_token(client=self.client)
            
            print("📊 Loading accounts...")
            self.accounts = get_accounts(self.client)
            
            # Initialize components
            self.position_analyzer = PositionAnalyzer()
            self.confirmation_card = ConfirmationCard(self.client)
            self.walk_engine = WalkLimitEngine(self.client)
            
            print(f"{Colors.GREEN}✅ Connected successfully!{Colors.END}")
            print(f"Found {len(self.accounts)} account(s)")
            
            # Auto-set default account if there's only one and none is set
            if not self.default_account and len(self.accounts) == 1:
                self.default_account = self.accounts[0].accountId
                print(f"{Colors.GREEN}✅ Auto-set default account: {self.default_account}{Colors.END}")
            elif self.default_account:
                print(f"Default account: {self.default_account}")
            else:
                print(f"{Colors.YELLOW}💡 Tip: Use 'set default account <id>' to set a default account{Colors.END}")
            
            print()
        
        except Exception as e:
            print(f"{Colors.RED}❌ Initialization failed: {e}{Colors.END}")
            sys.exit(1)
    
    def _setup_history(self):
        """Setup command history to enable up arrow navigation."""
        if READLINE_AVAILABLE:
            # Set up history file path
            history_file = os.path.expanduser("~/.public_brokerage_history")
            
            # Set history length
            readline.set_history_length(1000)
            
            # Try to read existing history
            try:
                readline.read_history_file(history_file)
            except FileNotFoundError:
                # History file doesn't exist yet, that's fine
                pass
            except Exception as e:
                print(f"{Colors.YELLOW}⚠️  Could not load command history: {e}{Colors.END}")
            
            # Set up automatic history saving on exit
            import atexit
            atexit.register(self._save_history, history_file)
            
            print(f"{Colors.GREEN}✅ Command history enabled (use up/down arrows){Colors.END}")
        else:
            print(f"{Colors.YELLOW}⚠️  Readline not available - command history disabled{Colors.END}")
    
    def _save_history(self, history_file):
        """Save command history to file."""
        if READLINE_AVAILABLE:
            try:
                readline.write_history_file(history_file)
            except Exception as e:
                print(f"{Colors.YELLOW}⚠️  Could not save command history: {e}{Colors.END}")
    
    def do_accounts(self, args):
        """List all available accounts."""
        try:
            ensure_access_token(self.client)
            
            print(f"\n{Colors.BOLD}📊 ACCOUNTS{Colors.END}")
            print("-" * 60)
            
            for i, account in enumerate(self.accounts, 1):
                default_marker = f" {Colors.YELLOW}*{Colors.END}" if account.accountId == self.default_account else ""
                print(f"{i}. {Colors.BOLD}{account.accountId}{Colors.END}{default_marker}")
                print(f"   Type: {account.accountType}")
                print(f"   Options Level: {account.optionsLevel}")
                print(f"   Account Type: {account.brokerageAccountType}")
                print(f"   Trade Permissions: {account.tradePermissions}")
                print()
        
        except Exception as e:
            print(f"{Colors.RED}❌ Error fetching accounts: {e}{Colors.END}")
    
    def do_set(self, args):
        """Set configuration options."""
        if not args:
            print("Usage: set default account <account_id>")
            return
        
        parts = shlex.split(args)
        if len(parts) >= 3 and parts[0] == "default" and parts[1] == "account":
            account_id = parts[2]
            
            # Validate account exists
            if not any(acc.accountId == account_id for acc in self.accounts):
                print(f"{Colors.RED}❌ Account {account_id} not found{Colors.END}")
                return
            
            config.set_default_account(account_id)
            self.default_account = account_id
            print(f"{Colors.GREEN}✅ Default account set to: {account_id}{Colors.END}")
        else:
            print("Usage: set default account <account_id>")
    
    def do_positions(self, args):
        """Show account positions."""
        account_id = args.strip() if args.strip() else self.default_account
        self._show_positions(account_id)
    
    def do_options(self, args):
        """Show option expirations for a symbol."""
        if not args:
            print("Usage: options <symbol>")
            return
        symbol = args.strip().upper()
        self._show_options(symbol)
    
    def do_chain(self, args):
        """Show option chain for a symbol and expiration."""
        if not args:
            print("Usage: chain <symbol> <expiration>")
            return
        
        parts = shlex.split(args)
        if len(parts) < 2:
            print("Usage: chain <symbol> <expiration>")
            return
        
        symbol = parts[0].upper()
        expiration = parts[1]
        self._show_option_chain(symbol, expiration)
    
    def do_quote(self, args):
        """Get real-time quote for a symbol."""
        if not args:
            print("Usage: quote <symbol>")
            return
        
        symbol = args.strip().upper()
        try:
            ensure_access_token(self.client)
            
            # Get account ID
            account_id = self.default_account
            if not account_id and self.accounts:
                account_id = self.accounts[0].accountId
            
            if not account_id:
                print(f"{Colors.RED}❌ No account available{Colors.END}")
                return
            
            # Create instrument object
            from public_brokerage.models.common import Instrument, InstrumentType
            instruments = [Instrument(symbol=symbol, type=InstrumentType.EQUITY)]
            
            quotes = get_quotes(self.client, account_id, instruments)
            
            if quotes and quotes[0].outcome == "SUCCESS":
                quote = quotes[0]
                print(f"\n{Colors.BOLD}💰 {symbol} Quote{Colors.END}")
                print("-" * 40)
                print(f"Last: {Colors.BOLD}${quote.last or 'N/A'}{Colors.END}")
                print(f"Bid:  ${quote.bid or 'N/A'} x {quote.bidSize or 0}")
                print(f"Ask:  ${quote.ask or 'N/A'} x {quote.askSize or 0}")
                if quote.volume:
                    print(f"Volume: {quote.volume:,}")
                if quote.openInterest:
                    print(f"Open Interest: {quote.openInterest:,}")
                if quote.lastTimestamp:
                    print(f"Last Updated: {quote.lastTimestamp}")
                print()
            else:
                print(f"{Colors.RED}❌ No quote found for {symbol}{Colors.END}")
        
        except Exception as e:
            print(f"{Colors.RED}❌ Error fetching quote: {e}{Colors.END}")
    
    def do_open_call_spread(self, args):
        """Open a call spread using walk limit orders."""
        parser = argparse.ArgumentParser(prog='open_call_spread', add_help=False)
        parser.add_argument('symbol', help='Underlying symbol (e.g., AAPL)')
        parser.add_argument('short_expiration', help='Short leg expiration (YYYY-MM-DD)')
        parser.add_argument('short_strike', type=float, help='Short leg strike price')
        parser.add_argument('long_expiration', help='Long leg expiration (YYYY-MM-DD)')
        parser.add_argument('long_strike', type=float, help='Long leg strike price')
        parser.add_argument('quantity', type=int, help='Number of spreads')
        parser.add_argument('--max_wait_time', type=int, default=42, help='Max wait time per price level (seconds)')
        parser.add_argument('--execute', action='store_true', help='Execute actual orders (default: dry run)')
        
        try:
            parsed_args = parser.parse_args(shlex.split(args))
        except SystemExit:
            print("Usage: open_call_spread <symbol> <short_exp> <short_strike> <long_exp> <long_strike> <qty> [--max_wait_time=42] [--execute]")
            return
        
        if not self.default_account:
            print(f"{Colors.RED}❌ No default account set. Use 'set default account <id>' first.{Colors.END}")
            return
        
        try:
            # Show confirmation card
            confirmed = self.confirmation_card.display_opening_spread_confirmation(
                parsed_args.symbol.upper(),
                parsed_args.short_expiration,
                parsed_args.short_strike,
                parsed_args.long_expiration,
                parsed_args.long_strike,
                parsed_args.quantity,
                parsed_args.max_wait_time,
                self.default_account,
                parsed_args.execute
            )
            
            if not confirmed:
                return
            
            # Start walk limit process
            process_id = self.walk_engine.start_open_call_spread_process(
                parsed_args.symbol.upper(),
                parsed_args.short_expiration,
                parsed_args.short_strike,
                parsed_args.long_expiration,
                parsed_args.long_strike,
                parsed_args.quantity,
                self.default_account,
                parsed_args.max_wait_time,
                parsed_args.execute
            )
            
            mode = "LIVE" if parsed_args.execute else "DRY RUN"
            print(f"{Colors.GREEN}🚀 Started {mode} call spread process: {process_id}{Colors.END}")
            print(f"Use 'status' to monitor progress")
        
        except Exception as e:
            print(f"{Colors.RED}❌ Error starting call spread process: {e}{Colors.END}")
    
    def do_close_call_spread(self, args):
        """Close call spreads using walk limit orders."""
        parser = argparse.ArgumentParser(prog='close_call_spread', add_help=False)
        parser.add_argument('symbol', help='Underlying symbol (e.g., AAPL)')
        parser.add_argument('--max_wait_time', type=int, default=42, help='Max wait time per price level (seconds)')
        parser.add_argument('--execute', action='store_true', help='Execute actual orders (default: dry run)')
        
        try:
            parsed_args = parser.parse_args(shlex.split(args))
        except SystemExit:
            print("Usage: close_call_spread <symbol> [--max_wait_time=42] [--execute]")
            return
        
        if not self.default_account:
            print(f"{Colors.RED}❌ No default account set. Use 'set default account <id>' first.{Colors.END}")
            return
        
        try:
            # Get current positions and analyze for spreads
            portfolio = get_account_portfolio(self.client, self.default_account)
            spreads = self.position_analyzer.find_call_spreads_for_symbol(
                portfolio.positions, 
                parsed_args.symbol.upper()
            )
            
            if not spreads:
                print(f"{Colors.YELLOW}📍 No call spreads found for {parsed_args.symbol.upper()}{Colors.END}")
                return
            
            # Check for existing close processes
            active_processes = self.walk_engine.get_all_processes()
            for process_id, process_info in active_processes.items():
                if (process_info['symbol'] == parsed_args.symbol.upper() and 
                    process_info['strategy'] == 'close_call_spread' and 
                    process_info['status'] in ['RUNNING', 'WAITING', 'STARTING']):
                    print(f"{Colors.YELLOW}⚠️  Close process already running for {parsed_args.symbol.upper()}: {process_id}{Colors.END}")
                    return
            
            # Show confirmation card
            confirmed = self.confirmation_card.display_closing_spread_confirmation(
                parsed_args.symbol.upper(),
                spreads,
                parsed_args.max_wait_time,
                self.default_account,
                parsed_args.execute
            )
            
            if not confirmed:
                return
            
            # Start close processes
            process_ids = self.walk_engine.start_close_call_spread_process(
                parsed_args.symbol.upper(),
                spreads,
                self.default_account,
                parsed_args.max_wait_time,
                parsed_args.execute
            )
            
            mode = "LIVE" if parsed_args.execute else "DRY RUN"
            print(f"{Colors.GREEN}🚀 Started {mode} close processes: {', '.join(process_ids)}{Colors.END}")
            print(f"Use 'status' to monitor progress")
        
        except Exception as e:
            print(f"{Colors.RED}❌ Error starting close spread process: {e}{Colors.END}")
    
    def do_status(self, args):
        """Show status of all background processes."""
        try:
            processes = self.walk_engine.get_all_processes()
            
            if not processes:
                print(f"{Colors.YELLOW}📋 No active processes{Colors.END}")
                return
            
            print(f"\n{Colors.BOLD}📋 BACKGROUND PROCESSES{Colors.END}")
            print("=" * 80)
            
            for process_id, info in processes.items():
                status_color = self._get_status_color(info['status'])
                filled_qty = info.get('quantity', 0) - info.get('remaining_quantity', 0)
                print(f"{Colors.BOLD}{process_id}{Colors.END} - {info['symbol']} {info['strategy']}")
                print(f"   Status: {status_color}{info['status']}{Colors.END}")
                print(f"   Progress: {info['attempts']}/{info['max_attempts']} attempts")
                print(f"   Quantity: {filled_qty}/{info.get('quantity', 0)} filled ({info.get('remaining_quantity', 0)} remaining)")
                print(f"   Current Price: ${info['current_price']:.2f}")
                print(f"   Last Update: {info['last_update']}")
                
                if info.get('messages'):
                    print(f"   Last Message: {info['messages'][-1]}")
                print()
        
        except Exception as e:
            print(f"{Colors.RED}❌ Error fetching process status: {e}{Colors.END}")
    
    def do_cancel(self, args):
        """Cancel background processes."""
        if not args:
            print("Usage: cancel <process_id> | cancel all")
            return
        
        if args.strip().lower() == "all":
            # Show what orders will be cancelled first
            active_orders = self.walk_engine.get_active_orders()
            if active_orders:
                print(f"{Colors.YELLOW}⚠️  About to cancel {len(active_orders)} active orders:{Colors.END}")
                for process_id, order_id in active_orders.items():
                    print(f"  Process {process_id[:8]}: Order {order_id}")
                
            # Use emergency cancellation for consistency and safety
            account_id = self.default_account
            if not account_id:
                print(f"{Colors.RED}❌ No default account set. Use 'set default account <id>' first{Colors.END}")
                return
                
            cancelled, failed = self.walk_engine.emergency_cancel_all_orders(account_id)
            if failed > 0:
                print(f"{Colors.YELLOW}⚠️  Cancelled {cancelled} orders, {failed} failed to cancel{Colors.END}")
            else:
                print(f"{Colors.GREEN}✅ Successfully cancelled all {cancelled} orders{Colors.END}")
        else:
            process_id = args.strip()
            if self.walk_engine.cancel_process(process_id):
                print(f"{Colors.GREEN}✅ Cancelled process {process_id}{Colors.END}")
            else:
                print(f"{Colors.RED}❌ Process {process_id} not found{Colors.END}")
    
    def do_logs(self, args):
        """Show logs for a specific process."""
        if not args:
            print("Usage: logs <process_id>")
            return
        
        process_id = args.strip()
        process_info = self.walk_engine.get_process_status(process_id)
        
        if not process_info:
            print(f"{Colors.RED}❌ Process {process_id} not found{Colors.END}")
            return
        
        print(f"\n{Colors.BOLD}📄 LOGS FOR PROCESS {process_id}{Colors.END}")
        print("-" * 60)
        
        if process_info['messages']:
            for message in process_info['messages']:
                print(message)
        else:
            print("No log messages")
        print()
    
    def do_help(self, args):
        """Show help for available commands."""
        print(f"\n{Colors.BOLD}📚 AVAILABLE COMMANDS{Colors.END}")
        print("=" * 60)
        
        commands = [
            ("accounts", "List all available accounts"),
            ("set default account <id>", "Set default account for operations"),
            ("positions [account_id]", "Show positions for account"),
            ("options <symbol>", "Show option expirations for symbol"),
            ("chain <symbol> <exp>", "Show option chain for symbol and expiration"),
            ("quote <symbol>", "Get real-time quote"),
            ("open_call_spread", "Open call spread with walk limit orders"),
            ("close_call_spread", "Close call spreads with walk limit orders"),
            ("status", "Show all background process status"),
            ("cancel <id|all>", "Cancel background processes and orders"),
            ("logs <process_id>", "Show process execution logs"),
            ("exit", "Exit the shell")
        ]
        
        for cmd_name, description in commands:
            print(f"{Colors.CYAN}{cmd_name:<25}{Colors.END} {description}")
        
        print(f"\n{Colors.BOLD}Examples:{Colors.END}")
        print("  open_call_spread AAPL 2024-07-19 170 2024-08-16 175 1 --execute")
        print("  close_call_spread AAPL --max_wait_time=60 --execute")
        print("  close_call_spread AAPL  # dry-run only (no --execute)")
        print()
    
    def do_exit(self, args):
        """Exit the shell."""
        # Check for active background processes
        if hasattr(self, 'walk_engine') and self.walk_engine.has_active_processes():
            print(f"{Colors.YELLOW}⏳ Waiting for background processes to complete...{Colors.END}")
            print("Use Ctrl+C to force exit")
            try:
                # First wait 30 seconds with timeout
                if self.walk_engine.wait_for_all_processes(timeout=30):
                    print(f"{Colors.GREEN}✅ All processes completed{Colors.END}")
                else:
                    # After 30 seconds, show message and wait indefinitely
                    print(f"{Colors.YELLOW}⏳ Still waiting for processes... Press Ctrl+C to force exit{Colors.END}")
                    if self.walk_engine.wait_for_all_processes(timeout=None):
                        print(f"{Colors.GREEN}✅ All processes completed{Colors.END}")
            except KeyboardInterrupt:
                print(f"{Colors.YELLOW}\n⚠️  Ctrl+C detected - Emergency cancelling all orders!{Colors.END}")
                if self.walk_engine and hasattr(self, 'default_account_id'):
                    try:
                        cancelled, failed = self.walk_engine.emergency_cancel_all_orders(self.default_account_id)
                        if cancelled > 0:
                            print(f"{Colors.GREEN}✅ Emergency cancelled {cancelled} orders{Colors.END}")
                        if failed > 0:
                            print(f"{Colors.RED}❌ Failed to cancel {failed} orders{Colors.END}")
                    except Exception as e:
                        print(f"{Colors.RED}❌ Error during emergency cancellation: {e}{Colors.END}")
                print(f"{Colors.YELLOW}⚠️  Force exiting with active processes{Colors.END}")
        
        print(f"{Colors.BOLD}👋 Goodbye!{Colors.END}")
        if self.client:
            self.client.close()
        return True
    
    def do_quit(self, args):
        """Exit the shell."""
        return self.do_exit(args)
    
    def default(self, line):
        """Handle unknown commands."""
        print(f"{Colors.RED}❌ Unknown command: {line}{Colors.END}")
        print("Type 'help' for available commands")
    
    def emptyline(self):
        """Handle empty lines."""
        pass
    
    def _show_positions(self, account_id: Optional[str]):
        """Show positions for an account."""
        if not account_id:
            print(f"{Colors.RED}❌ No account specified and no default account set{Colors.END}")
            return
        
        try:
            ensure_access_token(self.client)
            portfolio = get_account_portfolio(self.client, account_id)
            
            print(f"\n{Colors.BOLD}📍 POSITIONS FOR ACCOUNT {account_id}{Colors.END}")
            print("=" * 80)
            
            if not portfolio.positions:
                print(f"{Colors.YELLOW}📍 No positions found{Colors.END}")
                return
            
            # Analyze positions for spreads
            analysis = self.position_analyzer.analyze_positions(portfolio.positions)
            
            # Show spreads first
            if analysis['call_spreads']:
                print(f"{Colors.BOLD}📊 CALL SPREADS:{Colors.END}")
                for spread in analysis['call_spreads']:
                    summary = self.position_analyzer.get_spread_summary(spread)
                    print(f"  {summary['underlying']}: {summary['short_strike']}/{summary['long_strike']} "
                          f"x{summary['quantity']} (Exp: {summary['expiration']})")
                print()
            
            # Calculate total portfolio P&L
            total_current_value = 0.0
            total_pnl = 0.0
            
            for position in portfolio.positions:
                current_val = float(position.currentValue)
                cost_basis_val = float(position.costBasis.totalCost) if position.costBasis.totalCost else 0.0
                position_pnl = current_val - cost_basis_val
                
                total_current_value += current_val
                total_pnl += position_pnl
            
            # Show portfolio summary
            if portfolio.positions:
                cost_basis_total = total_current_value - total_pnl
                total_pnl_pct = (total_pnl / abs(cost_basis_total) * 100) if cost_basis_total != 0 else 0.0
                
                print(f"{Colors.BOLD}📊 PORTFOLIO SUMMARY:{Colors.END}")
                print(f"{'Current Value':<15} {'P&L':<12} {'%':<8}")
                print("-" * 40)
                
                pnl_color = Colors.GREEN if total_pnl > 0 else Colors.RED if total_pnl < 0 else Colors.END
                print(f"${total_current_value:<14.2f} "
                      f"{pnl_color}${total_pnl:<11.2f} {total_pnl_pct:<7.2f}%{Colors.END}")
                print()
            
            # Show individual positions
            print(f"{Colors.BOLD}📈 ALL POSITIONS:{Colors.END}")
            print(f"{'Symbol':<12} {'Qty':<8} {'Current':<12} {'P&L':<12} {'%':<10} {'Cost Basis':<12}")
            print("-" * 80)
            
            for position in portfolio.positions:
                quantity = float(position.quantity)
                current_val = float(position.currentValue)
                cost_basis_val = float(position.costBasis.totalCost) if position.costBasis.totalCost else 0.0
                
                # Calculate P&L as the difference between current value and cost basis
                # This should match what the UI shows
                pnl_val = current_val - cost_basis_val
                
                # Get percentage from cost basis gain (this should be more accurate)
                cost_basis_pnl_pct = float(position.costBasis.gainPercentage) if position.costBasis.gainPercentage else 0.0
                
                # Alternative: calculate percentage manually
                manual_pnl_pct = (pnl_val / abs(cost_basis_val) * 100) if cost_basis_val != 0 else 0.0
                
                # Use the cost basis percentage as it should match the UI
                pnl_pct = cost_basis_pnl_pct
                
                pnl_color = Colors.GREEN if pnl_val > 0 else Colors.RED if pnl_val < 0 else Colors.END
                qty_sign = "+" if quantity >= 0 else ""
                print(f"{position.instrument.symbol:<12} {qty_sign}{quantity:<7.0f} "
                      f"${current_val:<11.2f} "
                      f"{pnl_color}${pnl_val:<11.2f} {pnl_pct:<9.2f}%{Colors.END} "
                      f"${cost_basis_val:<11.2f}")
        
        except Exception as e:
            print(f"{Colors.RED}❌ Error fetching positions: {e}{Colors.END}")
    
    def _show_options(self, symbol: str):
        """Show option expirations for a symbol."""
        try:
            ensure_access_token(self.client)
            
            # Get account ID
            account_id = self.default_account
            if not account_id and self.accounts:
                account_id = self.accounts[0].accountId
            
            if not account_id:
                print(f"{Colors.RED}❌ No account available{Colors.END}")
                return
            
            # Create instrument object
            from public_brokerage.models.common import Instrument, InstrumentType
            instrument = Instrument(symbol=symbol.upper(), type=InstrumentType.EQUITY)
            
            # Get option expirations
            expirations = get_option_expirations(self.client, account_id, instrument)
            
            print(f"\n{Colors.BOLD}📅 OPTION EXPIRATIONS FOR {symbol.upper()}{Colors.END}")
            print("-" * 40)
            
            if expirations:
                for exp_date in expirations:
                    print(f"  {exp_date}")
                print(f"\nTotal: {len(expirations)} expiration dates")
            else:
                print(f"{Colors.YELLOW}No option expirations found{Colors.END}")
        
        except Exception as e:
            print(f"{Colors.RED}❌ Error fetching option expirations: {e}{Colors.END}")
    
    def _show_option_chain(self, symbol: str, expiration: str):
        """Show option chain for symbol and expiration."""
        try:
            ensure_access_token(self.client)
            
            # Get account ID
            account_id = self.default_account
            if not account_id and self.accounts:
                account_id = self.accounts[0].accountId
            
            if not account_id:
                print(f"{Colors.RED}❌ No account available{Colors.END}")
                return
            
            # Create instrument object
            from public_brokerage.models.common import Instrument, InstrumentType
            instrument = Instrument(symbol=symbol.upper(), type=InstrumentType.EQUITY)
            
            # Parse expiration date
            from datetime import datetime
            try:
                expiration_date = datetime.strptime(expiration, "%Y-%m-%d").date()
            except ValueError:
                print(f"{Colors.RED}❌ Invalid date format. Use YYYY-MM-DD (e.g., 2024-01-19){Colors.END}")
                return
            
            # Get current quote for the underlying to find ATM
            current_price = None
            try:
                underlying_instrument = Instrument(symbol=symbol.upper(), type=InstrumentType.EQUITY)
                quotes = get_quotes(self.client, account_id, [underlying_instrument])
                if quotes and len(quotes) > 0:
                    quote = quotes[0]
                    if hasattr(quote, 'last') and quote.last:
                        current_price = float(quote.last)
                    elif hasattr(quote, 'bid') and hasattr(quote, 'ask') and quote.bid and quote.ask:
                        current_price = (float(quote.bid) + float(quote.ask)) / 2
            except Exception as e:
                print(f"{Colors.YELLOW}⚠️  Could not get underlying price for ATM marking: {e}{Colors.END}")
            
            # Get option chain
            chain = get_option_chain(self.client, account_id, instrument, expiration_date)
            
            print(f"\n{Colors.BOLD}⛓️  OPTION CHAIN FOR {symbol.upper()} - {expiration}{Colors.END}")
            if current_price:
                print(f"{Colors.BOLD}📈 Underlying Price: ${current_price:.2f}{Colors.END}")
            print("=" * 100)
            
            if not chain.calls and not chain.puts:
                print(f"{Colors.YELLOW}No options found{Colors.END}")
                return
            
            
            # Helper function to extract strike price from option symbol
            def extract_strike_from_symbol(option_symbol: str) -> float:
                """Extract strike price from option symbol (condensed OSI format)."""
                try:
                    # Handle condensed format: SYMBOL + YYMMDD + C/P + 8-digit strike
                    # Find the last C or P in the symbol
                    call_pos = option_symbol.rfind('C')
                    put_pos = option_symbol.rfind('P')
                    
                    if call_pos == -1 and put_pos == -1:
                        return None
                    
                    # Get position of the option type indicator
                    type_pos = max(call_pos, put_pos)
                    
                    # Extract the 8-digit strike price after the type indicator
                    if len(option_symbol) >= type_pos + 9:  # Need at least 8 digits after type
                        strike_str = option_symbol[type_pos + 1:type_pos + 9]
                        strike_mills = int(strike_str)
                        return strike_mills / 1000.0
                    return None
                except (ValueError, IndexError):
                    return None
            
            # Find ATM strikes if we have current price
            atm_call_strike = None
            atm_put_strike = None
            if current_price:
                min_call_diff = float('inf')
                min_put_diff = float('inf')
                
                # Find ATM call
                if chain.calls:
                    for call in chain.calls:
                        if call.outcome == "SUCCESS":
                            strike = extract_strike_from_symbol(call.instrument.symbol)
                            if strike is not None:
                                diff = abs(strike - current_price)
                                if diff < min_call_diff:
                                    min_call_diff = diff
                                    atm_call_strike = strike
                
                # Find ATM put  
                if chain.puts:
                    for put in chain.puts:
                        if put.outcome == "SUCCESS":
                            strike = extract_strike_from_symbol(put.instrument.symbol)
                            if strike is not None:
                                diff = abs(strike - current_price)
                                if diff < min_put_diff:
                                    min_put_diff = diff
                                    atm_put_strike = strike

            # Display calls and puts
            print(f"\n{Colors.BOLD}📞 CALLS{Colors.END}")
            print("-" * 50)
            if chain.calls:
                for call in chain.calls:
                    if call.outcome == "SUCCESS":
                        strike = extract_strike_from_symbol(call.instrument.symbol)
                        # Mark ATM with star
                        atm_marker = " ⭐" if (atm_call_strike is not None and strike == atm_call_strike) else ""
                        print(f"  {call.instrument.symbol}: Last=${call.last or 'N/A'}, Bid=${call.bid or 'N/A'}, Ask=${call.ask or 'N/A'}{atm_marker}")
            else:
                print("  No calls available")
            
            print(f"\n{Colors.BOLD}📉 PUTS{Colors.END}")
            print("-" * 50)
            if chain.puts:
                for put in chain.puts:
                    if put.outcome == "SUCCESS":
                        strike = extract_strike_from_symbol(put.instrument.symbol)
                        # Mark ATM with star
                        atm_marker = " ⭐" if (atm_put_strike is not None and strike == atm_put_strike) else ""
                        print(f"  {put.instrument.symbol}: Last=${put.last or 'N/A'}, Bid=${put.bid or 'N/A'}, Ask=${put.ask or 'N/A'}{atm_marker}")
            else:
                print("  No puts available")
        
        except Exception as e:
            print(f"{Colors.RED}❌ Error fetching option chain: {e}{Colors.END}")
    
    def _format_currency(self, amount):
        """Format currency for display."""
        try:
            return f"${float(amount):,.2f}"
        except:
            return "N/A"
    
    def _format_change(self, change, change_percent):
        """Format price change with colors."""
        try:
            change_val = float(change)
            percent_val = float(change_percent)
            color = Colors.GREEN if change_val >= 0 else Colors.RED
            sign = "+" if change_val >= 0 else ""
            return f"{color}{sign}${change_val:.2f} ({sign}{percent_val:.2f}%){Colors.END}"
        except:
            return "N/A"
    
    def _get_status_color(self, status):
        """Get color for process status."""
        status_colors = {
            'RUNNING': Colors.BLUE,
            'WAITING': Colors.YELLOW,
            'FILLED': Colors.GREEN,
            'CANCELLED': Colors.RED,
            'FAILED': Colors.RED,
            'COMPLETED': Colors.GREEN
        }
        return status_colors.get(status, Colors.WHITE)


# Global reference to shell for signal handler
_shell_instance = None

def signal_handler(signum, frame):
    """Handle SIGINT (Ctrl+C) by cancelling all orders before exit."""
    print(f"\n{Colors.YELLOW}⚠️  Signal {signum} received - Emergency shutdown!{Colors.END}")
    if _shell_instance and _shell_instance.walk_engine and hasattr(_shell_instance, 'default_account'):
        try:
            account_id = _shell_instance.default_account
            if account_id:
                cancelled, failed = _shell_instance.walk_engine.emergency_cancel_all_orders(account_id)
                if cancelled > 0:
                    print(f"{Colors.GREEN}✅ Emergency cancelled {cancelled} orders{Colors.END}")
                if failed > 0:
                    print(f"{Colors.RED}❌ Failed to cancel {failed} orders{Colors.END}")
            else:
                print(f"{Colors.YELLOW}⚠️  No default account set - cannot cancel orders{Colors.END}")
        except Exception as e:
            print(f"{Colors.RED}❌ Error during emergency cancellation: {e}{Colors.END}")
    print(f"{Colors.BOLD}👋 Emergency exit complete!{Colors.END}")
    sys.exit(0)

def main():
    """Main entry point."""
    global _shell_instance
    
    # Set up signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    shell = None
    try:
        shell = PublicBrokerageShell()
        _shell_instance = shell  # Store for signal handler
        shell.cmdloop()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}⚠️  Ctrl+C detected - Emergency shutdown initiated!{Colors.END}")
        if shell and shell.walk_engine and hasattr(shell, 'default_account_id'):
            try:
                cancelled, failed = shell.walk_engine.emergency_cancel_all_orders(shell.default_account_id)
                if cancelled > 0:
                    print(f"{Colors.GREEN}✅ Emergency cancelled {cancelled} orders{Colors.END}")
                if failed > 0:
                    print(f"{Colors.RED}❌ Failed to cancel {failed} orders{Colors.END}")
            except Exception as e:
                print(f"{Colors.RED}❌ Error during emergency cancellation: {e}{Colors.END}")
        print(f"\n{Colors.BOLD}👋 Goodbye!{Colors.END}")
        sys.exit(0)
    except Exception as e:
        print(f"{Colors.RED}❌ Shell error: {e}{Colors.END}")
        if shell and shell.walk_engine and hasattr(shell, 'default_account_id'):
            try:
                shell.walk_engine.emergency_cancel_all_orders(shell.default_account_id)
            except:
                pass  # Don't let cleanup errors mask the original error
        sys.exit(1)


if __name__ == "__main__":
    main()
