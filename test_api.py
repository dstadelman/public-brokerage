#!/usr/bin/env python3
"""
Simple script to test the Public Brokerage API library.
Run this from the root directory: python test_api.py
"""

import os
from dotenv import load_dotenv

from public_brokerage.client import PublicBrokerageClient
from public_brokerage.auth import create_access_token
from public_brokerage.accounts import get_accounts

# Load environment variables
load_dotenv()

def main():
    """Test basic API functionality."""
    secret_token = os.getenv("PUBLIC_SECRET_TOKEN")
    
    if not secret_token:
        print("❌ Error: PUBLIC_SECRET_TOKEN environment variable is required")
        print("   Please copy .env.example to .env and add your secret token")
        return
    
    print("🚀 Testing Public Brokerage API Library")
    print("=" * 50)
    
    try:
        # Create client
        with PublicBrokerageClient(secret_token=secret_token, debug=False) as client:
            print("✅ Client created successfully")
            
            # Test authentication
            print("🔑 Testing authentication...")
            access_token = create_access_token(client=client)
            print(f"✅ Access token created: {access_token[:20]}...")
            
            # Test getting accounts
            print("📊 Getting accounts...")
            accounts = get_accounts(client)
            print(f"✅ Found {len(accounts)} account(s)")
            
            for i, account in enumerate(accounts, 1):
                print(f"   Account {i}: {account.accountId} ({account.accountType})")
            
            print("\n🎉 All tests passed! The library is working correctly.")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nNote: This test requires valid API credentials.")
        print("Make sure your PUBLIC_SECRET_TOKEN is correct and has API access enabled.")

if __name__ == "__main__":
    main()
